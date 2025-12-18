"""
Clean and transform SpecialChem JSONL data for database seeding
- Removes all URLs
- Transforms to match existing schema
- Handles missing values
- Preserves extra data
- Enhances descriptions using OpenAI
"""

import json
import re
import os
import asyncio
import aiohttp
import time
import unicodedata
from collections import defaultdict
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Configuration
INPUT_FILE = "output_specialChem_1765800534743.json"
OUTPUT_FILE = "cleaned_specialchem_ingredients.json"
CHECKPOINT_FILE = "cleaning_checkpoint.json"  # For resume capability
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""

if not OPENAI_API_KEY:
    print("⚠️  WARNING: OPENAI_API_KEY not found. Description enhancement will be skipped.")

# URL pattern for detection and removal
URL_PATTERN = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+|www\.[^\s<>"{}|\\^`\[\]]+',
    re.IGNORECASE
)

# Rate limiter
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
    
    async def wait_if_needed(self, model_name: str, rpm_limit: int):
        """Wait if we're approaching the rate limit"""
        current_time = time.time()
        minute_ago = current_time - 60
        
        self.requests[model_name] = [
            req_time for req_time in self.requests[model_name] 
            if req_time > minute_ago
        ]
        
        aggressive_limit = int(rpm_limit * 0.8)
        if len(self.requests[model_name]) >= aggressive_limit:
            wait_time = 60 - (current_time - self.requests[model_name][0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        
        self.requests[model_name].append(current_time)

rate_limiter = RateLimiter()


def normalize_unicode_text(text: str) -> str:
    """Normalize unicode characters to ASCII equivalents"""
    if not isinstance(text, str):
        return text
    # Normalize unicode characters (e.g., \u2019 -> ')
    # NFKD = Normalization Form Compatibility Decomposition
    text = unicodedata.normalize('NFKD', text)
    # Replace common unicode quotes and dashes with ASCII equivalents
    replacements = {
        '\u2019': "'",  # Right single quotation mark
        '\u2018': "'",  # Left single quotation mark
        '\u201C': '"',  # Left double quotation mark
        '\u201D': '"',  # Right double quotation mark
        '\u2013': '-',  # En dash
        '\u2014': '--', # Em dash
        '\u2026': '...', # Ellipsis
        '\u00A0': ' ',  # Non-breaking space
        '\u200B': '',   # Zero-width space
        '\u200C': '',   # Zero-width non-joiner
        '\u200D': '',   # Zero-width joiner
        '\uFEFF': '',   # Zero-width no-break space
    }
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)
    return text

def remove_urls_from_text(text: str) -> str:
    """Remove URLs from text string and normalize unicode"""
    if not isinstance(text, str):
        return text
    text = normalize_unicode_text(text)
    return URL_PATTERN.sub('', text).strip()


def remove_urls_from_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively remove URLs from dictionary"""
    cleaned = {}
    for key, value in data.items():
        if key in ['url', 'document_url', 'product_url']:
            continue  # Skip URL fields entirely
        
        if isinstance(value, str):
            cleaned[key] = remove_urls_from_text(value)
        elif isinstance(value, list):
            cleaned[key] = remove_urls_from_list(value)
        elif isinstance(value, dict):
            cleaned[key] = remove_urls_from_dict(value)
        else:
            cleaned[key] = value
    return cleaned


def remove_urls_from_list(data: List[Any]) -> List[Any]:
    """Recursively remove URLs from list"""
    cleaned = []
    for item in data:
        if isinstance(item, str):
            cleaned_item = remove_urls_from_text(item)
            if cleaned_item:  # Only add non-empty strings
                cleaned.append(cleaned_item)
        elif isinstance(item, dict):
            cleaned_item = remove_urls_from_dict(item)
            if cleaned_item:  # Only add non-empty dicts
                cleaned.append(cleaned_item)
        elif isinstance(item, list):
            cleaned_item = remove_urls_from_list(item)
            if cleaned_item:
                cleaned.append(cleaned_item)
        else:
            cleaned.append(item)
    return cleaned


def parse_inci_names(inci_raw: Optional[str], inci_list: Optional[List[Dict]]) -> List[str]:
    """Extract INCI names from raw string or list"""
    inci_names = []
    
    # First try to get from inci_raw (pipe-separated)
    if inci_raw and inci_raw.strip():
        names = [name.strip() for name in inci_raw.split('|') if name.strip()]
        inci_names.extend(names)
    
    # Also extract from inci list (if available and not already added)
    if inci_list:
        for inci_item in inci_list:
            if isinstance(inci_item, dict):
                name = inci_item.get('name', '').strip()
                if name and name not in inci_names:
                    inci_names.append(name)
            elif isinstance(inci_item, str) and inci_item.strip():
                if inci_item.strip() not in inci_names:
                    inci_names.append(inci_item.strip())
    
    return inci_names


def extract_category_tree(category_list: Optional[List[Dict]]) -> List[List[str]]:
    """Extract category names and create tree structure"""
    if not category_list:
        return []
    
    trees = []
    for item in category_list:
        if isinstance(item, dict):
            name = item.get('name', '').strip()
            if name:
                trees.append([name])  # Single-level tree
        elif isinstance(item, str) and item.strip():
            trees.append([item.strip()])
    
    return trees


def clean_text_field(value: Any) -> Any:
    """Clean and normalize text fields"""
    if isinstance(value, str):
        return normalize_unicode_text(value)
    elif isinstance(value, list):
        return [clean_text_field(item) for item in value]
    elif isinstance(value, dict):
        return {k: clean_text_field(v) for k, v in value.items()}
    return value

def clean_ingredient_record(raw_item: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and transform a single ingredient record"""
    
    # Remove URLs from all fields
    cleaned = remove_urls_from_dict(raw_item)
    
    # Normalize unicode in all text fields
    cleaned = clean_text_field(cleaned)
    
    # Extract INCI names
    inci_names = parse_inci_names(
        cleaned.get('inci_raw'),
        cleaned.get('inci', [])
    )
    
    # Extract functional category tree
    functionality_tree = extract_category_tree(cleaned.get('product_family', []))
    
    # Extract chemical class tree
    chemical_tree = extract_category_tree(cleaned.get('chemical_family', []))
    
    # Extract product type names
    product_type_names = []
    if cleaned.get('product_type'):
        for pt in cleaned.get('product_type', []):
            if isinstance(pt, dict):
                name = pt.get('name', '').strip()
                if name:
                    product_type_names.append(name)
            elif isinstance(pt, str) and pt.strip():
                product_type_names.append(pt.strip())
    
    # Clean application_formats (remove empty strings)
    application_formats = [
        fmt for fmt in cleaned.get('application_formats', [])
        if fmt and fmt.strip()
    ]
    
    # Build the cleaned record matching seed_db.py schema
    cleaned_record = {
        # Core schema fields (required by seed_db.py)
        "ingredient_name": cleaned.get('product_name', '').strip(),
        "original_inci_name": cleaned.get('inci_raw', '').strip(),
        "supplier": cleaned.get('supplier_name', '').strip(),
        "description": cleaned.get('description', '').strip(),
        "inci_names": inci_names,
        "functionality_category_tree": functionality_tree,
        "chemical_class_category_tree": chemical_tree,
        
        # Extra data to preserve (for later use)
        "extra_data": {
            "product_category": cleaned.get('product_category', '').strip(),
            "product_type": product_type_names,
            "product_family_raw": cleaned.get('product_family_raw', '').strip(),
            "product_type_raw": cleaned.get('product_type_raw', '').strip(),
            "characteristics": cleaned.get('characteristics', {}),
            "benefits": cleaned.get('benefits', []),
            "properties": cleaned.get('properties', []),
            "compliance": cleaned.get('compliance', []),
            "applications": cleaned.get('applications', []),
            "application_formats": application_formats,
            "documents": [
                {
                    "document_name": doc.get('document_name', '').strip(),
                    "remarks": doc.get('remarks', '').strip()
                }
                for doc in cleaned.get('documents', [])
                if doc.get('document_name', '').strip()
            ],
            "source": cleaned.get('source', 'specialchem')
        },
        
        # Fields for description enhancement
        "category_decided": None,  # Will be set by OpenAI
        "enhanced_description": None,  # Will be set by OpenAI
    }
    
    return cleaned_record


async def test_openai_connection(session: aiohttp.ClientSession) -> bool:
    """Test if OpenAI API is working and has credits"""
    if not OPENAI_API_KEY:
        return False
    
    try:
        # Quick test call with minimal tokens
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 5
        }
        
        async with session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                return True
            elif response.status == 401:
                print(f"\n❌ ERROR: Invalid OpenAI API key")
                return False
            elif response.status == 429:
                error_data = await response.json()
                error_msg = error_data.get("error", {}).get("message", "")
                if "insufficient_quota" in error_msg.lower() or "billing" in error_msg.lower():
                    print(f"\n❌ ERROR: OpenAI credits exhausted or billing issue")
                    print(f"   Message: {error_msg}")
                    return False
                else:
                    print(f"\n⚠️  WARNING: Rate limit hit, but API is working")
                    return True
            else:
                error_text = await response.text()
                print(f"\n⚠️  WARNING: OpenAI API returned status {response.status}")
                return False
    except Exception as e:
        print(f"\n⚠️  WARNING: Could not test OpenAI connection: {e}")
        return False

async def fill_missing_values_with_openai(
    session: aiohttp.ClientSession,
    ingredient_name: str,
    description: str,
    existing_inci: List[str],
    characteristics: Dict[str, Any],
    product_family: List[str],
    existing_compliance: List[str],
    existing_applications: List[str],
    existing_properties: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Call OpenAI to fill missing INCI names and other missing values"""
    
    if not OPENAI_API_KEY:
        return None
    
    clean_ingredient = str(ingredient_name or 'Unknown').strip()
    clean_description = str(description or 'No description available').strip()
    existing_inci_str = " | ".join(existing_inci) if existing_inci else "None"
    characteristics_str = json.dumps(characteristics, indent=2) if characteristics else "None"
    product_family_str = " | ".join(product_family) if product_family else "None"
    existing_compliance_str = " | ".join(existing_compliance) if existing_compliance else "None"
    existing_applications_str = " | ".join(existing_applications) if existing_applications else "None"
    
    prompt = f"""You are a cosmetic ingredient expert. Analyze this ingredient and extract missing information in EXACT JSON format.

INGREDIENT NAME: {clean_ingredient}
DESCRIPTION: {clean_description}
EXISTING INCI NAMES: {existing_inci_str}
CHARACTERISTICS: {characteristics_str}
PRODUCT FAMILY: {product_family_str}
EXISTING COMPLIANCE: {existing_compliance_str}
EXISTING APPLICATIONS: {existing_applications_str}

Provide a JSON response with these exact fields:
{{
    "inci_names": ["INCI Name 1", "INCI Name 2", ...],
    "functional_categories": ["Category 1", "Category 2", ...],
    "compliance": ["Compliance 1", "Compliance 2", ...],
    "applications": ["Application 1", "Application 2", ...],
    "properties": [
        {{"properties": "Property Name", "value_unit": "Value Unit", "test_condition": "", "test_method": ""}},
        ...
    ],
    "missing_data_filled": true
}}

RULES:
1. INCI NAMES: Extract all INCI (International Nomenclature of Cosmetic Ingredients) names from the ingredient name and description
   - If existing INCI names are provided, use them and add any additional ones found
   - If no INCI names exist, extract them from the ingredient name and description
   - Return as array of strings in proper INCI format (e.g., "HYALURONIC ACID", "SODIUM HYALURONATE")
   - If ingredient name itself is an INCI name, include it
   - Extract from description if mentioned (e.g., "contains X and Y" → extract X and Y as INCI)

2. FUNCTIONAL CATEGORIES: Extract functional categories from description and product family
   - Use existing product_family if provided
   - Extract additional categories from description (e.g., "moisturizing", "antioxidant", "emollient")
   - Return as array of category names
   - If no categories found, return empty array []

3. COMPLIANCE: Extract compliance and certification information from description and characteristics
   - Look for mentions of: COSMOS, REACH, Vegan, Organic, GMO-free, FDA, EU regulations, etc.
   - If existing compliance is provided, use it and add any additional ones found
   - Return as array of compliance strings (e.g., ["COSMOS", "Vegan", "REACH"])
   - If no compliance found, return empty array []

4. APPLICATIONS: Extract product applications from description
   - Look for mentions of: skin care, hair care, body care, facial care, sun care, baby care, etc.
   - If existing applications are provided, use them and add any additional ones found
   - Return as array of application strings (e.g., ["Skin Care", "Hair Care"])
   - If no applications found, return empty array []

5. PROPERTIES: Extract physical/chemical properties from description and characteristics
   - Look for: pH, viscosity, density, solubility, appearance, color, molecular weight, etc.
   - Return as array of objects with structure: {{"properties": "Property Name", "value_unit": "Value Unit", "test_condition": "", "test_method": ""}}
   - Extract values from description if mentioned (e.g., "pH 4-6" → {{"properties": "pH", "value_unit": "4 - 6"}})
   - If no properties found, return empty array []

IMPORTANT: 
- Output ONLY valid JSON, no other text, no markdown, no explanations
- Ensure JSON is properly formatted with double quotes
- Return empty arrays if no data can be extracted for a field
- If you cannot extract any data, return: {{"inci_names": [], "functional_categories": [], "compliance": [], "applications": [], "properties": [], "missing_data_filled": false}}"""

    # Model priority (GPT-5 first per user preference)
    models_to_try = [
        {"name": "gpt-5", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-chat-latest", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-mini", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-mini-2025-08-07", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-4.1", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "chatgpt-4o-latest", "max_tokens": 4000, "endpoint": "chat", "rpm": 200, "tpm": 500000},
        {"name": "gpt-4o-2024-11-20", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-3.5-turbo", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        endpoint = model_config["endpoint"]
        rpm_limit = model_config["rpm"]
        
        await rate_limiter.wait_if_needed(model_name, rpm_limit)
        await asyncio.sleep(1)
        
        try:
            if endpoint == "chat":
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}]
                }
                if model_name.startswith("gpt-5"):
                    payload["max_completion_tokens"] = max_tokens
                else:
                    payload["max_tokens"] = max_tokens
            else:
                payload = {
                    "model": model_name,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                    "top_p": 0.9
                }
            
            api_url = "https://api.openai.com/v1/chat/completions" if endpoint == "chat" else "https://api.openai.com/v1/completions"
            
            async with session.post(
                api_url,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    if not data or "choices" not in data:
                        continue
                    
                    if endpoint == "chat":
                        content = data["choices"][0]["message"]["content"].strip()
                    else:
                        content = data["choices"][0]["text"].strip()
                    
                    # Try to extract JSON from response
                    json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group())
                            if "inci_names" in result:
                                return result
                        except json.JSONDecodeError:
                            pass
                    
                    # If direct JSON parse fails, try to parse the whole content
                    try:
                        result = json.loads(content)
                        if "inci_names" in result:
                            return result
                    except json.JSONDecodeError:
                        continue
                
                elif response.status == 429:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "")
                    if "insufficient_quota" in error_msg.lower() or "billing" in error_msg.lower():
                        # Credits exhausted - don't try other models
                        return {"error": "insufficient_quota", "message": error_msg}
                    continue
                elif response.status == 401:
                    # Invalid API key - don't try other models
                    return {"error": "invalid_key"}
                else:
                    continue
                    
        except Exception as e:
            continue
    
    return None


async def enhance_description_with_openai(
    session: aiohttp.ClientSession,
    ingredient_name: str,
    description: str
) -> Optional[Dict[str, Any]]:
    """Call OpenAI to enhance description and determine category"""
    
    if not OPENAI_API_KEY:
        return None
    
    clean_ingredient = str(ingredient_name or 'Unknown').strip()
    clean_description = str(description or 'No description available').strip()
    
    prompt = f"""You are a cosmetic ingredient expert. Analyze this ingredient and provide a response in EXACT JSON format.

INGREDIENT: {clean_ingredient}
DESCRIPTION: {clean_description}

Provide a JSON response with these exact fields:
{{
    "category": "Active" or "Excipient",
    "description": "Enhanced description (~100 words for Active, ~50 for Excipient)"
}}

IMPORTANT: 
- Output ONLY valid JSON, no other text, no markdown, no explanations
- Use "Active" for functional ingredients (vitamins, peptides, acids, etc.)
- Use "Excipient" for non-functional ingredients (thickeners, preservatives, etc.)
- Keep descriptions concise but informative
- Ensure JSON is properly formatted with double quotes
- If you cannot analyze the ingredient, return: {{"category": "Unknown", "description": "Unable to analyze this ingredient"}}"""

    # Model priority (GPT-5 first per user preference)
    models_to_try = [
        {"name": "gpt-5", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-chat-latest", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-mini", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-mini-2025-08-07", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-4.1", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "chatgpt-4o-latest", "max_tokens": 4000, "endpoint": "chat", "rpm": 200, "tpm": 500000},
        {"name": "gpt-4o-2024-11-20", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-3.5-turbo", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        endpoint = model_config["endpoint"]
        rpm_limit = model_config["rpm"]
        
        await rate_limiter.wait_if_needed(model_name, rpm_limit)
        await asyncio.sleep(1)  # Small delay between requests
        
        try:
            if endpoint == "chat":
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}]
                }
                if model_name.startswith("gpt-5"):
                    payload["max_completion_tokens"] = max_tokens
                else:
                    payload["max_tokens"] = max_tokens
            else:
                payload = {
                    "model": model_name,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                    "top_p": 0.9
                }
            
            api_url = "https://api.openai.com/v1/chat/completions" if endpoint == "chat" else "https://api.openai.com/v1/completions"
            
            async with session.post(
                api_url,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    if not data or "choices" not in data:
                        continue
                    
                    if endpoint == "chat":
                        content = data["choices"][0]["message"]["content"].strip()
                    else:
                        content = data["choices"][0]["text"].strip()
                    
                    # Try to extract JSON from response
                    json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group())
                            if "category" in result and "description" in result:
                                return result
                        except json.JSONDecodeError:
                            pass
                    
                    # If direct JSON parse fails, try to parse the whole content
                    try:
                        result = json.loads(content)
                        if "category" in result and "description" in result:
                            return result
                    except json.JSONDecodeError:
                        continue
                
                elif response.status == 429:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "")
                    if "insufficient_quota" in error_msg.lower() or "billing" in error_msg.lower():
                        # Credits exhausted - don't try other models
                        return {"error": "insufficient_quota", "message": error_msg}
                    continue  # Try next model
                elif response.status == 401:
                    # Invalid API key - don't try other models
                    return {"error": "invalid_key"}
                else:
                    continue  # Try next model
                    
        except Exception as e:
            continue  # Try next model
    
    return None


async def process_ingredient_with_enhancement(
    session: aiohttp.ClientSession,
    cleaned_record: Dict[str, Any]
) -> Dict[str, Any]:
    """Process ingredient: fill missing values and enhance description"""
    
    ingredient_name = cleaned_record.get("ingredient_name", "")
    description = cleaned_record.get("description", "")
    existing_inci = cleaned_record.get("inci_names", [])
    characteristics = cleaned_record.get("extra_data", {}).get("characteristics", {})
    product_family = [
        cat[0] if isinstance(cat, list) and len(cat) > 0 else str(cat)
        for cat in cleaned_record.get("functionality_category_tree", [])
    ]
    existing_compliance = cleaned_record.get("extra_data", {}).get("compliance", [])
    existing_applications = cleaned_record.get("extra_data", {}).get("applications", [])
    existing_properties = cleaned_record.get("extra_data", {}).get("properties", [])
    
    # Fill missing values if OpenAI is available
    # Note: use global OPENAI_API_KEY here, not local variable
    global OPENAI_API_KEY
    if OPENAI_API_KEY and ingredient_name:
        try:
            # Check if we need to fill any missing data
            needs_inci_fill = not existing_inci or not cleaned_record.get("original_inci_name", "").strip()
            needs_category_fill = not product_family
            needs_compliance_fill = not existing_compliance
            needs_applications_fill = not existing_applications
            needs_properties_fill = not existing_properties
            
            if needs_inci_fill or needs_category_fill or needs_compliance_fill or needs_applications_fill or needs_properties_fill:
                fill_result = await fill_missing_values_with_openai(
                    session,
                    ingredient_name,
                    description,
                    existing_inci,
                    characteristics,
                    product_family,
                    existing_compliance,
                    existing_applications,
                    existing_properties
                )
                
                # Check for credits exhausted error
                if fill_result and fill_result.get("error") == "insufficient_quota":
                    # Return error to stop processing
                    return {"error": "insufficient_quota", "message": fill_result.get("message", "")}
                
                if fill_result and fill_result.get("missing_data_filled"):
                    # Merge extracted INCI names (normalize unicode)
                    extracted_inci = fill_result.get("inci_names", [])
                    if extracted_inci:
                        # Normalize and combine
                        normalized_extracted = [normalize_unicode_text(name) for name in extracted_inci]
                        combined_inci = list(set(existing_inci + normalized_extracted))
                        cleaned_record["inci_names"] = combined_inci
                        
                        # Update original_inci_name if it was missing
                        if not cleaned_record.get("original_inci_name", "").strip():
                            cleaned_record["original_inci_name"] = " | ".join(combined_inci)
                    
                    # Merge extracted functional categories (normalize unicode)
                    extracted_categories = fill_result.get("functional_categories", [])
                    if extracted_categories:
                        normalized_categories = [normalize_unicode_text(cat) for cat in extracted_categories]
                        combined_categories = list(set(product_family + normalized_categories))
                        # Convert to tree format
                        cleaned_record["functionality_category_tree"] = [[cat] for cat in combined_categories]
                    
                    # Merge extracted compliance (normalize unicode)
                    extracted_compliance = fill_result.get("compliance", [])
                    if extracted_compliance:
                        normalized_compliance = [normalize_unicode_text(comp) for comp in extracted_compliance]
                        combined_compliance = list(set(existing_compliance + normalized_compliance))
                        cleaned_record["extra_data"]["compliance"] = combined_compliance
                    
                    # Merge extracted applications (normalize unicode)
                    extracted_applications = fill_result.get("applications", [])
                    if extracted_applications:
                        normalized_apps = [normalize_unicode_text(app) for app in extracted_applications]
                        combined_applications = list(set(existing_applications + normalized_apps))
                        cleaned_record["extra_data"]["applications"] = combined_applications
                    
                    # Merge extracted properties (normalize unicode in text fields)
                    extracted_properties = fill_result.get("properties", [])
                    if extracted_properties:
                        # Normalize unicode in property objects
                        normalized_props = []
                        for prop in extracted_properties:
                            normalized_prop = {}
                            for k, v in prop.items():
                                normalized_prop[k] = normalize_unicode_text(v) if isinstance(v, str) else v
                            normalized_props.append(normalized_prop)
                        
                        # Combine properties, avoiding duplicates based on property name
                        existing_prop_names = {prop.get("properties", "") for prop in existing_properties}
                        new_properties = [
                            prop for prop in normalized_props
                            if prop.get("properties", "") not in existing_prop_names
                        ]
                        cleaned_record["extra_data"]["properties"] = existing_properties + new_properties
        except Exception as e:
            print(f"⚠️  Error filling missing values for {ingredient_name}: {e}")
    
    # Enhance description if OpenAI is available
    if OPENAI_API_KEY and ingredient_name and description:
        try:
            result = await enhance_description_with_openai(
                session,
                ingredient_name,
                description
            )
            
            if result and "category" in result and "description" in result:
                cleaned_record["category_decided"] = result["category"]
                # Normalize unicode in enhanced description
                cleaned_record["enhanced_description"] = normalize_unicode_text(result["description"])
        except Exception as e:
            print(f"⚠️  Error enhancing description for {ingredient_name}: {e}")
    
    return cleaned_record


def validate_record(record: Dict[str, Any]) -> bool:
    """Validate that record has minimum required fields"""
    # Must have ingredient_name
    if not record.get("ingredient_name", "").strip():
        return False
    
    # Must have supplier
    if not record.get("supplier", "").strip():
        return False
    
    # Should have at least INCI name or original_inci_name
    if not record.get("inci_names") and not record.get("original_inci_name", "").strip():
        # Use ingredient_name as fallback for original_inci_name
        if not record.get("original_inci_name", "").strip():
            record["original_inci_name"] = record.get("ingredient_name", "")
    
    return True


def load_checkpoint() -> Dict[str, Any]:
    """Load checkpoint if exists"""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_checkpoint(checkpoint_data: Dict[str, Any]):
    """Save checkpoint"""
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, indent=2)

async def main():
    """Main processing function"""
    
    print("=" * 80)
    print("SpecialChem Data Cleaning & Enhancement")
    print("=" * 80)
    print(f"📥 Input file: {INPUT_FILE}")
    print(f"📤 Output file: {OUTPUT_FILE}")
    print(f"💾 Checkpoint file: {CHECKPOINT_FILE}")
    print(f"🤖 OpenAI enhancement: {'✅ Enabled' if OPENAI_API_KEY else '❌ Disabled'}")
    if not OPENAI_API_KEY:
        print(f"   ⚠️  WARNING: Missing OPENAI_API_KEY - enhancement will be skipped")
    print("=" * 80)
    
    # Check for existing checkpoint
    checkpoint = load_checkpoint()
    start_index = checkpoint.get("last_processed_index", 0)
    existing_cleaned = checkpoint.get("cleaned_data", [])
    checkpoint_total = checkpoint.get("total_records", 0)
    
    if start_index > 0 and os.path.exists(CHECKPOINT_FILE):
        print(f"\n🔄 CHECKPOINT FOUND - Resuming from previous run")
        print(f"   📊 Progress: {start_index}/{checkpoint_total} records already processed ({start_index*100/checkpoint_total:.1f}%)")
        print(f"   ✅ Already cleaned: {len(existing_cleaned)} records")
        print(f"   ⏭️  Continuing from record {start_index + 1}...")
        print(f"   📁 Checkpoint file: {CHECKPOINT_FILE}")
    else:
        print("\n🆕 Starting fresh (no checkpoint found)")
    
    # Read input file
    print("\n📖 Reading input file...")
    raw_data = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    raw_data.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"⚠️  Error parsing line {line_num}: {e}")
                    continue
    
    total_records = len(raw_data)
    print(f"✅ Loaded {total_records} records")
    
    # Use existing cleaned data if resuming
    cleaned_data = existing_cleaned if start_index > 0 else []
    
    # Clean and transform data (skip already processed if resuming)
    print("\n🧹 Cleaning and transforming data...")
    skipped_count = checkpoint.get("skipped_count", 0)
    
    # Create progress bar with detailed info
    pbar = tqdm(
        enumerate(raw_data[start_index:], start=start_index),
        desc="🧹 Cleaning",
        total=total_records,
        initial=start_index,
        unit="records",
        ncols=100,
        bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
    )
    
    for current_index, raw_item in pbar:
        try:
            cleaned_record = clean_ingredient_record(raw_item)
            
            # Validate record
            if validate_record(cleaned_record):
                cleaned_data.append(cleaned_record)
                pbar.set_postfix({
                    'cleaned': len(cleaned_data),
                    'skipped': skipped_count,
                    'valid': f"{len(cleaned_data)*100/(current_index+1):.1f}%"
                })
            else:
                skipped_count += 1
                pbar.set_postfix({
                    'cleaned': len(cleaned_data),
                    'skipped': skipped_count,
                    'valid': f"{len(cleaned_data)*100/(current_index+1):.1f}%"
                })
            
            # Save checkpoint every 100 records
            if (current_index + 1) % 100 == 0:
                save_checkpoint({
                    "last_processed_index": current_index + 1,
                    "total_records": total_records,
                    "cleaned_data": cleaned_data,
                    "skipped_count": skipped_count
                })
                pbar.set_description(f"🧹 Cleaning (saved @ {current_index + 1})")
        except Exception as e:
            print(f"\n⚠️  Error cleaning record {current_index + 1}: {e}")
            skipped_count += 1
            pbar.set_postfix({
                'cleaned': len(cleaned_data),
                'skipped': skipped_count,
                'error': 'yes'
            })
            continue
    
    pbar.close()
    print(f"\n✅ Cleaning Complete!")
    print(f"   ✅ Cleaned: {len(cleaned_data)} records")
    print(f"   ⚠️  Skipped: {skipped_count} invalid records")
    print(f"   📊 Success rate: {len(cleaned_data)*100/total_records:.1f}%")
    
    # Fill missing values and enhance descriptions if OpenAI is available
    use_openai = bool(OPENAI_API_KEY)
    
    if use_openai:
        print("\n🤖 Testing OpenAI API connection...")
        async with aiohttp.ClientSession() as test_session:
            api_working = await test_openai_connection(test_session)
        
        if not api_working:
            print(f"\n❌ OpenAI API is not working (credits exhausted or invalid key)")
            print(f"   ⏭️  Skipping enhancement - will only clean data")
            print(f"   💡 You can still use the cleaned data, just without enhanced descriptions")
            use_openai = False  # Disable enhancement for this run
        else:
            print(f"✅ OpenAI API connection successful")
        
        if use_openai:
            # Count Active vs Excipient
            active_records = [r for r in cleaned_data if r.get("category_decided") == "Active"]
            excipient_records = [r for r in cleaned_data if r.get("category_decided") == "Excipient"]
            uncategorized = [r for r in cleaned_data if r.get("category_decided") not in ["Active", "Excipient"]]
            
            print("\n🤖 Filling missing values and enhancing descriptions with OpenAI...")
            print(f"   🟢 Active ingredients: {len(active_records)} (will be enhanced)")
            print(f"   🔵 Excipient ingredients: {len(excipient_records)} (will be SKIPPED to save costs)")
            if uncategorized:
                print(f"   ⚠️  Uncategorized: {len(uncategorized)} (will be SKIPPED)")
            print(f"   💰 Cost savings: Only processing {len(active_records)}/{len(cleaned_data)} records ({len(active_records)*100/len(cleaned_data):.1f}%)")
            
            enhanced_count = checkpoint.get("enhanced_count", 0)
            filled_inci_count = checkpoint.get("filled_inci_count", 0)
            filled_category_count = checkpoint.get("filled_category_count", 0)
            filled_compliance_count = checkpoint.get("filled_compliance_count", 0)
            filled_applications_count = checkpoint.get("filled_applications_count", 0)
            filled_properties_count = checkpoint.get("filled_properties_count", 0)
            failed_count = checkpoint.get("failed_count", 0)
            credits_exhausted = checkpoint.get("credits_exhausted", False)
            skipped_excipients = checkpoint.get("skipped_excipients", len(excipient_records) + len(uncategorized))
            
            if credits_exhausted:
                print(f"\n❌ CREDITS EXHAUSTED - Enhancement stopped")
                print(f"   ✅ Already enhanced: {enhanced_count} Active ingredients before credits ran out")
                print(f"   ⏭️  Remaining Active records will be cleaned but not enhanced")
                use_openai = False  # Disable further enhancement
            else:
                # Check which records still need enhancement
                enhancement_start = checkpoint.get("enhancement_start_index", 0)
                if enhancement_start > 0:
                    print(f"🔄 Resuming enhancement from record {enhancement_start + 1}")
                    print(f"   ✅ Already enhanced: {enhanced_count} Active ingredients")
                    print(f"   ✅ Already filled INCI: {filled_inci_count}")
                    print(f"   ✅ Already filled categories: {filled_category_count}")
                    print(f"   ⏭️  Skipped Excipients: {skipped_excipients}")
                
                print(f"\n📊 Enhancement Status (ACTIVE INGREDIENTS ONLY):")
                print(f"   Total Active records to enhance: {len(active_records)}")
                print(f"   Starting from: {enhancement_start}")
                print(f"   Remaining: {len(active_records) - enhancement_start}")
                print(f"\n💡 Watch the progress bar below - it shows:")
                print(f"   - enhanced: descriptions successfully enhanced")
                print(f"   - filled_inci: missing INCI names filled")
                print(f"   - filled_cat: missing categories filled")
                print(f"   - filled_comp: missing compliance filled")
                print(f"   - filled_apps: missing applications filled")
                print(f"   - filled_props: missing properties filled")
                print(f"   - failed: records that failed enhancement\n")
        
            # Process in batches to avoid overwhelming the API
            # Only process Active ingredients
            active_data = [r for r in cleaned_data if r.get("category_decided") == "Active"]
            
            if not active_data:
                print(f"\n⚠️  No Active ingredients found to enhance!")
                print(f"   💡 Run categorize_ingredients.py first to categorize ingredients")
                use_openai = False
            else:
                batch_size = 50
                total_batches = (len(active_data) - enhancement_start + batch_size - 1) // batch_size
                
                async with aiohttp.ClientSession() as session:
                    pbar = tqdm(
                        range(enhancement_start, len(active_data), batch_size),
                        desc="🤖 Enhancing (Actives Only)",
                        initial=enhancement_start // batch_size,
                        total=total_batches,
                        unit="batch",
                        ncols=100,
                        bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} batches [{elapsed}<{remaining}, {rate_fmt}]'
                    )
                    
                    for i in pbar:
                        batch = active_data[i:i + batch_size]
                        tasks = [
                            process_ingredient_with_enhancement(session, record)
                            for record in batch
                        ]
                        
                        try:
                            results = await asyncio.gather(*tasks, return_exceptions=True)
                            
                            credits_exhausted_detected = False
                            for j, result in enumerate(results):
                                if isinstance(result, Exception):
                                    failed_count += 1
                                    continue
                                
                                # Check for credits exhausted error
                                if isinstance(result, dict) and result.get("error") == "insufficient_quota":
                                    credits_exhausted_detected = True
                                    print(f"\n❌ CREDITS EXHAUSTED detected!")
                                    print(f"   Message: {result.get('message', 'Insufficient quota')}")
                                    print(f"   ⏭️  Stopping enhancement - will continue with cleaning only")
                                    break
                                
                                # Track what was filled/enhanced
                                original_inci_count = len(batch[j].get("inci_names", []))
                                new_inci_count = len(result.get("inci_names", []))
                                if new_inci_count > original_inci_count:
                                    filled_inci_count += 1
                                
                                original_cat_count = len(batch[j].get("functionality_category_tree", []))
                                new_cat_count = len(result.get("functionality_category_tree", []))
                                if new_cat_count > original_cat_count:
                                    filled_category_count += 1
                                
                                # Track compliance, applications, properties
                                original_compliance = len(batch[j].get("extra_data", {}).get("compliance", []))
                                new_compliance = len(result.get("extra_data", {}).get("compliance", []))
                                if new_compliance > original_compliance:
                                    filled_compliance_count += 1
                                
                                original_apps = len(batch[j].get("extra_data", {}).get("applications", []))
                                new_apps = len(result.get("extra_data", {}).get("applications", []))
                                if new_apps > original_apps:
                                    filled_applications_count += 1
                                
                                original_props = len(batch[j].get("extra_data", {}).get("properties", []))
                                new_props = len(result.get("extra_data", {}).get("properties", []))
                                if new_props > original_props:
                                    filled_properties_count += 1
                                
                                if result.get("enhanced_description"):
                                    enhanced_count += 1
                                else:
                                    failed_count += 1
                                
                                # Update the original record in cleaned_data using the index mapping
                                batch_record = batch[j]
                                # Find the index in cleaned_data
                                for idx, orig_record in enumerate(cleaned_data):
                                    if id(orig_record) == id(batch_record):
                                        cleaned_data[idx] = result
                                        break
                            
                            # Stop if credits exhausted
                            if credits_exhausted_detected:
                                save_checkpoint({
                                    "last_processed_index": total_records,
                                    "total_records": total_records,
                                    "cleaned_data": cleaned_data,
                                    "skipped_count": skipped_count,
                                    "enhancement_start_index": i + batch_size,
                                    "enhanced_count": enhanced_count,
                                    "filled_inci_count": filled_inci_count,
                                    "filled_category_count": filled_category_count,
                                    "filled_compliance_count": filled_compliance_count,
                                    "filled_applications_count": filled_applications_count,
                                    "filled_properties_count": filled_properties_count,
                                    "failed_count": failed_count,
                                    "credits_exhausted": True,
                                    "skipped_excipients": skipped_excipients
                                })
                                break
                            
                            # Update progress bar with detailed stats
                            active_processed = i + batch_size
                            pbar.set_postfix({
                                'enhanced': enhanced_count,
                                'inci': filled_inci_count,
                                'cat': filled_category_count,
                                'comp': filled_compliance_count,
                                'apps': filled_applications_count,
                                'props': filled_properties_count,
                                'failed': failed_count,
                                'rate': f"{enhanced_count*100/active_processed:.1f}%" if active_processed > 0 else "0%"
                            })
                            
                            # Print sample of what was enhanced every 10 batches
                            if (i // batch_size) % 10 == 0 and enhanced_count > 0:
                                # Find a recently enhanced record to show
                                for j in range(min(batch_size, len(results))):
                                    if j < len(results) and not isinstance(results[j], Exception):
                                        result = results[j]
                                        if result.get("enhanced_description"):
                                            name = result.get("ingredient_name", "Unknown")[:40]
                                            category = result.get("category_decided", "N/A")
                                            print(f"\n   ✅ Enhanced: {name} → Category: {category}")
                                            break
                            
                            # Save checkpoint after each batch
                            save_checkpoint({
                                "last_processed_index": total_records,
                                "total_records": total_records,
                                "cleaned_data": cleaned_data,
                                "skipped_count": skipped_count,
                                "enhancement_start_index": i + batch_size,
                                "enhanced_count": enhanced_count,
                                "filled_inci_count": filled_inci_count,
                                "filled_category_count": filled_category_count,
                                "filled_compliance_count": filled_compliance_count,
                                "filled_applications_count": filled_applications_count,
                                "filled_properties_count": filled_properties_count,
                                "failed_count": failed_count,
                                "skipped_excipients": skipped_excipients
                            })
                            pbar.set_description(f"🤖 Enhancing Actives (saved @ {i + batch_size})")
                        except Exception as e:
                            print(f"\n⚠️  Error processing batch {i//batch_size + 1}: {e}")
                            failed_count += len(batch)
                            pbar.set_postfix({'error': 'yes', 'failed': failed_count})
                    
                    pbar.close()
        
        if use_openai and active_data:
            print(f"\n🤖 Enhancement Complete (ACTIVE INGREDIENTS ONLY)!")
            active_total = len([r for r in cleaned_data if r.get("category_decided") == "Active"])
            print(f"   🟢 Active ingredients processed: {active_total}")
            print(f"   ✅ Enhanced descriptions: {enhanced_count}/{active_total} ({enhanced_count*100/active_total:.1f}% of Actives)")
            print(f"   ✅ Filled missing INCI names: {filled_inci_count} Active ingredients")
            print(f"   ✅ Filled missing categories: {filled_category_count} Active ingredients")
            print(f"   ✅ Filled missing compliance: {filled_compliance_count} Active ingredients")
            print(f"   ✅ Filled missing applications: {filled_applications_count} Active ingredients")
            print(f"   ✅ Filled missing properties: {filled_properties_count} Active ingredients")
            print(f"   ⏭️  Skipped Excipients: {skipped_excipients} (to save costs)")
        
        # Count total records with data
        total_with_compliance = sum(1 for r in cleaned_data if r.get("extra_data", {}).get("compliance"))
        total_with_applications = sum(1 for r in cleaned_data if r.get("extra_data", {}).get("applications"))
        total_with_properties = sum(1 for r in cleaned_data if r.get("extra_data", {}).get("properties"))
        
        print(f"\n📊 Final Statistics:")
        print(f"   Records with compliance data: {total_with_compliance}/{len(cleaned_data)} ({total_with_compliance*100/len(cleaned_data):.1f}%)")
        print(f"   Records with applications: {total_with_applications}/{len(cleaned_data)} ({total_with_applications*100/len(cleaned_data):.1f}%)")
        print(f"   Records with properties: {total_with_properties}/{len(cleaned_data)} ({total_with_properties*100/len(cleaned_data):.1f}%)")
        
        if failed_count > 0:
            print(f"⚠️  Failed to process {failed_count} ingredients")
    else:
        print("\n⏭️  Skipping description enhancement (OpenAI API key not found)")
    
    # Write output file
    print(f"\n💾 Writing output to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
    
    # Count what was actually saved
    saved_enhanced = sum(1 for r in cleaned_data if r.get("enhanced_description"))
    saved_with_extra = sum(1 for r in cleaned_data if r.get("extra_data"))
    
    print(f"✅ Successfully wrote {len(cleaned_data)} cleaned records to {OUTPUT_FILE}")
    print(f"   📝 Records with enhanced_description: {saved_enhanced}")
    print(f"   📦 Records with extra_data: {saved_with_extra}")
    
    # Remove checkpoint file on successful completion
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print(f"🗑️  Removed checkpoint file (processing complete)")
    
    # Quick verification
    print(f"\n🔍 Quick Verification:")
    print(f"   File size: {os.path.getsize(OUTPUT_FILE) / 1024 / 1024:.2f} MB")
    print(f"   You can check the file to see 'enhanced_description' and 'category_decided' fields")
    print(f"   Sample command: python -c \"import json; d=json.load(open('{OUTPUT_FILE}')); print('Enhanced:', sum(1 for r in d if r.get('enhanced_description')))\"")
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total input records: {len(raw_data)}")
    print(f"Valid cleaned records: {len(cleaned_data)}")
    print(f"Skipped records: {skipped_count}")
    
    if OPENAI_API_KEY:
        enhanced = sum(1 for r in cleaned_data if r.get("enhanced_description"))
        print(f"Enhanced descriptions: {enhanced}/{len(cleaned_data)}")
    
    print("\n✅ Cleaning complete!")
    print(f"📁 Output file: {OUTPUT_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

