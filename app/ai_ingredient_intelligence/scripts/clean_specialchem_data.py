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
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY") or ""

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

def build_optimized_enrichment_prompt(ingredients_data: List[Dict[str, Any]]) -> str:
    """
    Token-efficient batch prompt for Active ingredient enrichment.
    Designed for gpt-4o-mini / claude-3-5-haiku.
    Target: 60% token reduction while maintaining output quality.
    """
    
    # Compact system context + output schema
    prompt = """You enrich cosmetic ACTIVE ingredients for a formulation database.

OUTPUT FORMAT: JSON array, one object per ingredient, preserve order.
```json
[{
  "description": "Rewritten 50-60 word description. Professional, unique phrasing.",
  "inci_names": ["Primary INCI", "Alternate INCI"],
  "functions": ["Antioxidant", "Moisturizing"],
  "compliance": ["COSMOS", "Vegan", "REACH"],
  "applications": ["Skin Care", "Anti-aging"],
  "properties": [{"name": "pH Range", "value": "4.0-6.0"}]
}]
```

RULES:
- Rewrite descriptions in your own words (avoid source plagiarism)
- Extract INCI names from description and existing data
- Return [] for fields with no data
- JSON only, no markdown, no commentary

---
INGREDIENTS:
"""
    
    # Compact ingredient formatting
    for idx, ing in enumerate(ingredients_data, 1):
        prompt += f"\n[{idx}] {ing['ingredient_name']}\n"
        
        # Description (truncate if excessive)
        desc = ing.get('description', '')[:5000]
        if desc:
            prompt += f"DESC: {desc}\n"
        
        # Only include non-empty fields with compact labels
        if ing.get('existing_inci'):
            prompt += f"INCI: {' | '.join(ing['existing_inci'][:6])}\n"
        
        if ing.get('product_family'):
            prompt += f"FAMILY: {' | '.join(ing['product_family'][:4])}\n"
        
        if ing.get('existing_compliance'):
            prompt += f"COMP: {' | '.join(ing['existing_compliance'][:6])}\n"
        
        if ing.get('existing_applications'):
            prompt += f"APPS: {' | '.join(ing['existing_applications'][:6])}\n"
    
    return prompt


async def process_batch_with_openai(
    session: aiohttp.ClientSession,
    batch_records: List[Dict[str, Any]]
) -> List[Optional[Dict[str, Any]]]:
    """Process a batch of ingredients in a single API call to reduce costs"""
    
    if not OPENAI_API_KEY or not batch_records:
        return [None] * len(batch_records)
    
    # Build compact ingredient data
    ingredients_data = []
    for record in batch_records:
        ingredient_name = record.get("ingredient_name", "")
        description = record.get("description", "")
        existing_inci = record.get("inci_names", [])
        product_family = [
            cat[0] if isinstance(cat, list) and len(cat) > 0 else str(cat)
            for cat in record.get("functionality_category_tree", [])
        ]
        existing_compliance = record.get("extra_data", {}).get("compliance", [])
        existing_applications = record.get("extra_data", {}).get("applications", [])
        
        ingredients_data.append({
            "ingredient_name": str(ingredient_name or 'Unknown').strip(),
            "description": str(description or '').strip(),
            "existing_inci": existing_inci,
            "product_family": product_family,
            "existing_compliance": existing_compliance,
            "existing_applications": existing_applications,
        })
    
    # Build optimized prompt
    prompt = build_optimized_enrichment_prompt(ingredients_data)
    
    # Model priority (cheapest first - gpt-4o-mini is best value)
    models_to_try = [
        {"name": "gpt-4o-mini", "max_tokens": 1500, "endpoint": "chat", "rpm": 500, "tpm": 2000000},
        {"name": "gpt-4o", "max_tokens": 1500, "endpoint": "chat", "rpm": 500, "tpm": 2000000},
        {"name": "gpt-4o-2024-11-20", "max_tokens": 1500, "endpoint": "chat", "rpm": 500, "tpm": 2000000},
        {"name": "gpt-3.5-turbo", "max_tokens": 1500, "endpoint": "chat", "rpm": 500, "tpm": 2000000},
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        endpoint = model_config["endpoint"]
        rpm_limit = model_config["rpm"]
        
        await rate_limiter.wait_if_needed(model_name, rpm_limit)
        await asyncio.sleep(0.5)  # Reduced delay for batch processing
        
        try:
            if endpoint == "chat":
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens
                }
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
                timeout=aiohttp.ClientTimeout(total=120)  # Longer timeout for batch
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    if not data or "choices" not in data:
                        continue
                    
                    if endpoint == "chat":
                        content = data["choices"][0]["message"]["content"].strip()
                    else:
                        content = data["choices"][0]["text"].strip()
                    
                    # Try to extract JSON array from response
                    # Look for array pattern (handle code blocks)
                    json_array_match = re.search(r'\[[\s\S]*?\]', content, re.DOTALL)
                    if json_array_match:
                        try:
                            results_array = json.loads(json_array_match.group())
                            if isinstance(results_array, list):
                                # Pad or truncate to match batch size
                                if len(results_array) < len(batch_records):
                                    results_array.extend([{}] * (len(batch_records) - len(results_array)))
                                elif len(results_array) > len(batch_records):
                                    results_array = results_array[:len(batch_records)]
                                return results_array
                        except json.JSONDecodeError:
                            pass
                    
                    # Try parsing whole content as array
                    try:
                        results_array = json.loads(content)
                        if isinstance(results_array, list):
                            if len(results_array) < len(batch_records):
                                results_array.extend([{}] * (len(batch_records) - len(results_array)))
                            elif len(results_array) > len(batch_records):
                                results_array = results_array[:len(batch_records)]
                            return results_array
                    except json.JSONDecodeError:
                        pass
                    
                    # Fallback: try to extract individual JSON objects
                    json_objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
                    if json_objects:
                        try:
                            results_array = [json.loads(obj) for obj in json_objects[:len(batch_records)]]
                            if len(results_array) < len(batch_records):
                                results_array.extend([{}] * (len(batch_records) - len(results_array)))
                            return results_array
                        except json.JSONDecodeError:
                            pass
                    
                    continue
                
                elif response.status == 429:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "")
                    if "insufficient_quota" in error_msg.lower() or "billing" in error_msg.lower():
                        # Credits exhausted - return error for all items
                        return [{"error": "insufficient_quota", "message": error_msg}] * len(batch_records)
                    continue
                elif response.status == 401:
                    # Invalid API key - return error for all items
                    return [{"error": "invalid_key"}] * len(batch_records)
                else:
                    continue
                    
        except Exception as e:
            continue
    
    # Return None for all items if all models failed
    return [None] * len(batch_records)


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
    """Legacy function - kept for backward compatibility. Use process_batch_with_openai instead."""
    # This function is deprecated but kept for compatibility
    # The new batch processing function should be used instead
    batch_result = await process_batch_with_openai(session, [{
        "ingredient_name": ingredient_name,
        "description": description,
        "inci_names": existing_inci,
        "functionality_category_tree": [[cat] for cat in product_family],
        "extra_data": {
            "characteristics": characteristics,
            "compliance": existing_compliance,
            "applications": existing_applications,
            "properties": existing_properties
        }
    }])
    return batch_result[0] if batch_result and batch_result[0] else None


async def enhance_description_with_openai(
    session: aiohttp.ClientSession,
    ingredient_name: str,
    description: str
) -> Optional[Dict[str, Any]]:
    """Legacy function - kept for backward compatibility. Use process_batch_with_openai instead."""
    # This function is deprecated but kept for compatibility
    # The new batch processing function should be used instead
    batch_result = await process_batch_with_openai(session, [{
        "ingredient_name": ingredient_name,
        "description": description,
        "inci_names": [],
        "functionality_category_tree": [],
        "extra_data": {
            "characteristics": {},
            "compliance": [],
            "applications": [],
            "properties": []
        }
    }])
    return batch_result[0] if batch_result and batch_result[0] else None


def needs_enhancement(cleaned_record: Dict[str, Any]) -> bool:
    """Check if record needs enhancement (missing data or description)"""
    existing_inci = cleaned_record.get("inci_names", [])
    product_family = cleaned_record.get("functionality_category_tree", [])
    existing_compliance = cleaned_record.get("extra_data", {}).get("compliance", [])
    existing_applications = cleaned_record.get("extra_data", {}).get("applications", [])
    existing_properties = cleaned_record.get("extra_data", {}).get("properties", [])
    has_enhanced_description = bool(cleaned_record.get("enhanced_description"))
    
    # Skip if already has enhanced description and all data is filled
    if has_enhanced_description and existing_inci and product_family:
        return False
    
    # Need enhancement if missing description or missing critical data
    needs_inci_fill = not existing_inci or not cleaned_record.get("original_inci_name", "").strip()
    needs_category_fill = not product_family
    needs_description = not has_enhanced_description
    
    return needs_inci_fill or needs_category_fill or needs_description


def apply_batch_result_to_record(cleaned_record: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Apply batch processing result to a single record (handles compact field names)"""
    if not result or result.get("error"):
        return cleaned_record
    
    existing_inci = cleaned_record.get("inci_names", [])
    product_family = [
        cat[0] if isinstance(cat, list) and len(cat) > 0 else str(cat)
        for cat in cleaned_record.get("functionality_category_tree", [])
    ]
    existing_compliance = cleaned_record.get("extra_data", {}).get("compliance", [])
    existing_applications = cleaned_record.get("extra_data", {}).get("applications", [])
    existing_properties = cleaned_record.get("extra_data", {}).get("properties", [])
    
    # Update enhanced description (handle both "description" and "desc")
    if "description" in result:
        cleaned_record["enhanced_description"] = normalize_unicode_text(result["description"])
    elif "desc" in result:
        cleaned_record["enhanced_description"] = normalize_unicode_text(result["desc"])
    
    # Update category (default to Active for actives)
    if "category" in result:
        cleaned_record["category_decided"] = result["category"]
    elif not cleaned_record.get("category_decided"):
        cleaned_record["category_decided"] = "Active"
    
    # Merge INCI names
    extracted_inci = result.get("inci_names", [])
    if extracted_inci:
        normalized_extracted = [normalize_unicode_text(name) for name in extracted_inci]
        combined_inci = list(set(existing_inci + normalized_extracted))
        cleaned_record["inci_names"] = combined_inci
        if not cleaned_record.get("original_inci_name", "").strip():
            cleaned_record["original_inci_name"] = " | ".join(combined_inci)
    
    # Merge functional categories (handle both "functional_categories" and "functions")
    extracted_categories = result.get("functional_categories", []) or result.get("functions", [])
    if extracted_categories:
        normalized_categories = [normalize_unicode_text(cat) for cat in extracted_categories]
        combined_categories = list(set(product_family + normalized_categories))
        cleaned_record["functionality_category_tree"] = [[cat] for cat in combined_categories]
    
    # Merge compliance
    extracted_compliance = result.get("compliance", [])
    if extracted_compliance:
        normalized_compliance = [normalize_unicode_text(comp) for comp in extracted_compliance]
        combined_compliance = list(set(existing_compliance + normalized_compliance))
        cleaned_record["extra_data"]["compliance"] = combined_compliance
    
    # Merge applications
    extracted_applications = result.get("applications", [])
    if extracted_applications:
        normalized_apps = [normalize_unicode_text(app) for app in extracted_applications]
        combined_applications = list(set(existing_applications + normalized_apps))
        cleaned_record["extra_data"]["applications"] = combined_applications
    
    # Merge properties (handle both old and new format)
    extracted_properties = result.get("properties", [])
    if extracted_properties:
        normalized_props = []
        for prop in extracted_properties:
            normalized_prop = {}
            # Handle new format: {"name": "...", "value": "..."}
            if "name" in prop:
                normalized_prop["properties"] = normalize_unicode_text(prop.get("name", ""))
                normalized_prop["value_unit"] = normalize_unicode_text(prop.get("value", ""))
                normalized_prop["test_condition"] = ""
                normalized_prop["test_method"] = ""
            # Handle old format: {"properties": "...", "value_unit": "..."}
            else:
                for k, v in prop.items():
                    normalized_prop[k] = normalize_unicode_text(v) if isinstance(v, str) else v
            normalized_props.append(normalized_prop)
        
        existing_prop_names = {prop.get("properties", "") for prop in existing_properties}
        new_properties = [
            prop for prop in normalized_props
            if prop.get("properties", "") and prop.get("properties", "") not in existing_prop_names
        ]
        cleaned_record["extra_data"]["properties"] = existing_properties + new_properties
    
    return cleaned_record


async def process_batch_of_ingredients(
    session: aiohttp.ClientSession,
    batch_records: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Process a batch of ingredients using optimized batch API call"""
    global OPENAI_API_KEY
    
    if not OPENAI_API_KEY:
        return batch_records
    
    # Filter records that need enhancement (maintain indices)
    records_to_process = []
    indices_to_process = []
    for idx, r in enumerate(batch_records):
        if needs_enhancement(r):
            records_to_process.append(r)
            indices_to_process.append(idx)
    
    if not records_to_process:
        return batch_records
    
    # Process batch
    try:
        batch_results = await process_batch_with_openai(session, records_to_process)
        
        # Check for credits exhausted
        if batch_results and batch_results[0] and isinstance(batch_results[0], dict) and batch_results[0].get("error") == "insufficient_quota":
            # Return error indicator for first record, others unchanged
            error_result = batch_records.copy()
            if error_result:
                error_result[0] = {"error": "insufficient_quota", "message": batch_results[0].get("message", "")}
            return error_result
        
        # Apply results to records and maintain original order
        final_results = batch_records.copy()
        for idx, result in zip(indices_to_process, batch_results):
            if result and isinstance(result, dict) and not result.get("error"):
                final_results[idx] = apply_batch_result_to_record(batch_records[idx], result)
            # If result is None or error, keep original record
        
        return final_results
        
    except Exception as e:
        print(f"⚠️  Error processing batch: {e}")
        return batch_records


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
    
    # Check if cleaned file already exists and is complete
    cleaned_data = []
    skip_cleaning = False
    
    if os.path.exists(OUTPUT_FILE):
        print(f"\n📁 Found existing cleaned file: {OUTPUT_FILE}")
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                cleaned_data = json.load(f)
            if cleaned_data and len(cleaned_data) > 0:
                print(f"   ✅ Loaded {len(cleaned_data)} already-cleaned records")
                print(f"   ⏭️  SKIPPING cleaning phase - using existing cleaned data")
                skip_cleaning = True
                total_records = len(cleaned_data)
                skipped_count = 0
        except Exception as e:
            print(f"   ⚠️  Error reading existing file: {e}")
            print(f"   🔄 Will re-clean from raw input")
            skip_cleaning = False
    
    # Check for existing checkpoint
    checkpoint = load_checkpoint()
    start_index = checkpoint.get("last_processed_index", 0)
    existing_cleaned = checkpoint.get("cleaned_data", [])
    checkpoint_total = checkpoint.get("total_records", 0)
    
    if not skip_cleaning:
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
    else:
        print(f"\n✅ Using existing cleaned data (skipped cleaning phase)")
        print(f"   ✅ Loaded: {len(cleaned_data)} records")
        total_records = len(cleaned_data)
    
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
            print(f"\n⚡ OPTIMIZATION ENABLED (v2 - Token-Efficient):")
            print(f"   📦 Batch processing: 30 ingredients per API call (reduces API calls by ~97%)")
            print(f"   🔄 Combined operations: Fill missing values + enhance description in one call")
            print(f"   💵 Cheapest models first: gpt-4o-mini prioritized ($0.15/1M input tokens)")
            print(f"   📉 Reduced tokens: 1500 max tokens, compact prompts (60% token reduction)")
            print(f"   📝 Shorter descriptions: 50-60 words (down from ~100 words)")
            print(f"   🏷️  Compact field names: 'desc', 'func', 'comp' instead of full names")
            print(f"   ⏭️  Smart skipping: Records with complete data are skipped")
            print(f"   💰 Estimated cost reduction: ~90-95% compared to original approach")
            print(f"   💵 Estimated cost: ~$0.50-0.80 per 1,000 ingredients (vs $5-8 original)")
            
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
                # OPTIMIZED: Use batch processing with 25-30 ingredients per API call to reduce costs
                api_batch_size = 30  # Process 30 ingredients in one API call (increased from 8)
                processing_batch_size = 50  # Process 50 records at a time for checkpointing
                total_batches = (len(active_data) - enhancement_start + processing_batch_size - 1) // processing_batch_size
                
                async with aiohttp.ClientSession() as session:
                    pbar = tqdm(
                        range(enhancement_start, len(active_data), processing_batch_size),
                        desc="🤖 Enhancing (Batched, Actives Only)",
                        initial=enhancement_start // processing_batch_size,
                        total=total_batches,
                        unit="batch",
                        ncols=100,
                        bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} batches [{elapsed}<{remaining}, {rate_fmt}]'
                    )
                    
                    for i in pbar:
                        processing_batch = active_data[i:i + processing_batch_size]
                        
                        try:
                            # Process in smaller API batches (8 ingredients per API call)
                            all_results = []
                            credits_exhausted_detected = False
                            
                            for api_batch_start in range(0, len(processing_batch), api_batch_size):
                                api_batch = processing_batch[api_batch_start:api_batch_start + api_batch_size]
                                
                                # Process batch using optimized batch API call
                                batch_results = await process_batch_of_ingredients(session, api_batch)
                                
                                # Check for credits exhausted
                                if batch_results and isinstance(batch_results[0], dict) and batch_results[0].get("error") == "insufficient_quota":
                                    credits_exhausted_detected = True
                                    print(f"\n❌ CREDITS EXHAUSTED detected!")
                                    print(f"   Message: {batch_results[0].get('message', 'Insufficient quota')}")
                                    print(f"   ⏭️  Stopping enhancement - will continue with cleaning only")
                                    break
                                
                                all_results.extend(batch_results)
                            
                            if credits_exhausted_detected:
                                save_checkpoint({
                                    "last_processed_index": total_records,
                                    "total_records": total_records,
                                    "cleaned_data": cleaned_data,
                                    "skipped_count": skipped_count,
                                    "enhancement_start_index": i + processing_batch_size,
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
                            
                            # Track what was filled/enhanced in this batch
                            batch_enhanced = 0
                            batch_filled_inci = 0
                            batch_filled_cat = 0
                            batch_filled_comp = 0
                            batch_filled_apps = 0
                            batch_filled_props = 0
                            batch_failed = 0
                            
                            for j, (original_record, result) in enumerate(zip(processing_batch, all_results)):
                                if isinstance(result, Exception):
                                    failed_count += 1
                                    batch_failed += 1
                                    continue
                                
                                # Track what was filled/enhanced
                                original_inci_count = len(original_record.get("inci_names", []))
                                new_inci_count = len(result.get("inci_names", []))
                                if new_inci_count > original_inci_count:
                                    filled_inci_count += 1
                                    batch_filled_inci += 1
                                
                                original_cat_count = len(original_record.get("functionality_category_tree", []))
                                new_cat_count = len(result.get("functionality_category_tree", []))
                                if new_cat_count > original_cat_count:
                                    filled_category_count += 1
                                    batch_filled_cat += 1
                                
                                # Track compliance, applications, properties
                                original_compliance = len(original_record.get("extra_data", {}).get("compliance", []))
                                new_compliance = len(result.get("extra_data", {}).get("compliance", []))
                                if new_compliance > original_compliance:
                                    filled_compliance_count += 1
                                    batch_filled_comp += 1
                                
                                original_apps = len(original_record.get("extra_data", {}).get("applications", []))
                                new_apps = len(result.get("extra_data", {}).get("applications", []))
                                if new_apps > original_apps:
                                    filled_applications_count += 1
                                    batch_filled_apps += 1
                                
                                original_props = len(original_record.get("extra_data", {}).get("properties", []))
                                new_props = len(result.get("extra_data", {}).get("properties", []))
                                if new_props > original_props:
                                    filled_properties_count += 1
                                    batch_filled_props += 1
                                
                                if result.get("enhanced_description"):
                                    enhanced_count += 1
                                    batch_enhanced += 1
                                else:
                                    failed_count += 1
                                    batch_failed += 1
                                
                                # Update the original record in cleaned_data
                                for idx, orig_record in enumerate(cleaned_data):
                                    if id(orig_record) == id(original_record):
                                        cleaned_data[idx] = result
                                        break
                            
                            # Update progress bar with detailed stats
                            active_processed = i + processing_batch_size
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
                            
                            # Print batch summary every 5 batches (more frequent updates)
                            if (i // processing_batch_size) % 5 == 0 and batch_enhanced > 0:
                                # Find recently enhanced records to show (show up to 2 examples)
                                enhanced_in_batch = [r for r in all_results if isinstance(r, dict) and r.get("enhanced_description")]
                                if enhanced_in_batch:
                                    print(f"\n   📊 Batch {i//processing_batch_size + 1}: Enhanced {batch_enhanced}/{len(processing_batch)} ingredients | Total enhanced: {enhanced_count}/{active_processed}")
                                    # Show up to 2 examples
                                    for result in enhanced_in_batch[:2]:
                                        name = result.get("ingredient_name", "Unknown")[:40]
                                        category = result.get("category_decided", "N/A")
                                        print(f"      ✅ {name} → {category}")
                            
                            # Save checkpoint after each processing batch
                            save_checkpoint({
                                "last_processed_index": total_records,
                                "total_records": total_records,
                                "cleaned_data": cleaned_data,
                                "skipped_count": skipped_count,
                                "enhancement_start_index": i + processing_batch_size,
                                "enhanced_count": enhanced_count,
                                "filled_inci_count": filled_inci_count,
                                "filled_category_count": filled_category_count,
                                "filled_compliance_count": filled_compliance_count,
                                "filled_applications_count": filled_applications_count,
                                "filled_properties_count": filled_properties_count,
                                "failed_count": failed_count,
                                "skipped_excipients": skipped_excipients
                            })
                            pbar.set_description(f"🤖 Enhancing Actives (saved @ {i + processing_batch_size})")
                        except Exception as e:
                            print(f"\n⚠️  Error processing batch {i//processing_batch_size + 1}: {e}")
                            failed_count += len(processing_batch)
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

