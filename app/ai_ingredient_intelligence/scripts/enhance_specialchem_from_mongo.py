"""
Enhance SpecialChem ingredients directly from MongoDB
This script processes only ingredients with source='specialchem' in extra_data
Works with data already seeded to MongoDB - no JSON file needed!
"""

import os
import asyncio
import aiohttp
import time
import re
import unicodedata
from collections import defaultdict
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm
from typing import Optional, Dict, Any, List, Tuple
from bson.objectid import ObjectId
import json

# Load .env variables
load_dotenv()

MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin")
DB_NAME: str = os.getenv("DB_NAME", "skin_bb")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY") or ""

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is missing. Please set it in your .env file.")

# Mongo client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db["ingre_branded_ingredients"]
inci_col = db["ingre_inci"]
func_cat_col = db["ingre_functional_categories"]

# Caches for async operations
inci_cache = {}  # normalized INCI name -> ObjectId
func_cat_cache = {}  # normalized category name -> ObjectId

def normalize_text(s: str) -> str:
    """Remove accents, lowercase, collapse spaces for search normalization."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()

async def get_or_create_inci(name: Optional[str]) -> Optional[ObjectId]:
    """Create/find an INCI by name; also stores a normalized variant for fast search."""
    if not name:
        return None
    norm = normalize_text(name)
    if norm in inci_cache:
        return inci_cache[norm]
    doc = await inci_col.find_one({"inciName_normalized": norm}, {"_id": 1})
    if doc:
        _id = doc["_id"]
    else:
        result = await inci_col.insert_one({"inciName": name, "inciName_normalized": norm})
        _id = result.inserted_id
    inci_cache[norm] = _id
    return _id

async def get_or_create_func_category(name: Optional[str]) -> Optional[ObjectId]:
    """Create/find a functional category by name."""
    if not name:
        return None
    norm = normalize_text(name)
    if norm in func_cat_cache:
        return func_cat_cache[norm]
    doc = await func_cat_col.find_one({"functionalName_normalized": norm}, {"_id": 1})
    if doc:
        _id = doc["_id"]
    else:
        result = await func_cat_col.insert_one({
            "functionalName": name,
            "functionalName_normalized": norm,
            "parent_id": None
        })
        _id = result.inserted_id
    func_cat_cache[norm] = _id
    return _id

# Rate limiter
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
    
    async def wait_if_needed(self, model_name: str, rpm_limit: int):
        current_time = time.time()
        minute_ago = current_time - 60
        self.requests[model_name] = [req_time for req_time in self.requests[model_name] if req_time > minute_ago]
        aggressive_limit = int(rpm_limit * 0.8)
        if len(self.requests[model_name]) >= aggressive_limit:
            wait_time = 60 - (current_time - self.requests[model_name][0]) + 1
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        self.requests[model_name].append(current_time)

rate_limiter = RateLimiter()

async def enhance_ingredient_batch(
    session: aiohttp.ClientSession,
    ingredients: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Enhance a batch of ingredients using OpenAI"""
    
    if not ingredients:
        return []
    
    # Build compact prompt for batch
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
    
    for idx, ing in enumerate(ingredients, 1):
        prompt += f"\n[{idx}] {ing.get('ingredient_name', 'Unknown')}\n"
        desc = ing.get('description', '')[:5000]
        if desc:
            prompt += f"DESC: {desc}\n"
        # Get existing INCI names from inci_ids if available
        existing_inci_names = ing.get('inci_names', [])
        if not existing_inci_names and ing.get('inci_ids'):
            # Fetch INCI names from database
            inci_ids = ing.get('inci_ids', [])
            inci_docs = await inci_col.find({"_id": {"$in": inci_ids}}, {"inciName": 1}).to_list(length=10)
            existing_inci_names = [doc.get("inciName", "") for doc in inci_docs if doc.get("inciName")]
        if existing_inci_names:
            prompt += f"INCI: {' | '.join(existing_inci_names[:6])}\n"
        # Get existing functional categories
        if ing.get('functionality_category_tree'):
            func_cats = [
                cat[0] if isinstance(cat, list) and len(cat) > 0 else str(cat)
                for cat in ing.get('functionality_category_tree', [])
            ]
            if func_cats:
                prompt += f"FAMILY: {' | '.join(func_cats[:4])}\n"
        if ing.get('extra_data', {}).get('compliance'):
            prompt += f"COMP: {' | '.join(ing['extra_data']['compliance'][:6])}\n"
    
    # Try models in order (only models we have access to)
    # Skip gpt-4o-mini if you get 403 errors - remove it from the list
    # Increased max_tokens to handle larger batches (30 ingredients * ~150 tokens each = ~4500, with buffer)
    models = [
        {"name": "gpt-4o", "max_tokens": 8000, "rpm": 500},
        {"name": "gpt-3.5-turbo", "max_tokens": 8000, "rpm": 500},
    ]
    
    for model_config in models:
        await rate_limiter.wait_if_needed(model_config["name"], model_config["rpm"])
        await asyncio.sleep(0.1)  # Reduced delay from 0.5s to 0.1s
        
        try:
            payload = {
                "model": model_config["name"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": model_config["max_tokens"]
            }
            
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    
                    # SIMPLE: Remove markdown code blocks
                    if content.startswith('```json'):
                        content = content[7:].strip()
                    elif content.startswith('```'):
                        content = content[3:].strip()
                    if content.endswith('```'):
                        content = content[:-3].strip()
                    
                    # SIMPLE: Find first [ and last ] and extract JSON
                    first_bracket = content.find('[')
                    last_bracket = content.rfind(']')
                    
                    if first_bracket >= 0 and last_bracket > first_bracket:
                        json_str = content[first_bracket:last_bracket + 1]
                        try:
                            json_match = json.loads(json_str)
                            if isinstance(json_match, list):
                                # Log if we got fewer results than expected
                                if len(json_match) < len(ingredients):
                                    print(f"  ⚠️  API returned {len(json_match)}/{len(ingredients)} results (response may be truncated)")
                                # Pad or truncate to match batch size
                                while len(json_match) < len(ingredients):
                                    json_match.append({})
                                if len(json_match) > len(ingredients):
                                    json_match = json_match[:len(ingredients)]
                                return json_match
                        except json.JSONDecodeError as e:
                            # JSON might be truncated - try to extract valid objects
                            error_pos = getattr(e, 'pos', None)
                            if error_pos:
                                # Try to parse up to the error position
                                try:
                                    # Find the last complete object before the error
                                    truncated_json = json_str[:error_pos]
                                    # Find the last complete object
                                    last_complete_obj = truncated_json.rfind('}')
                                    if last_complete_obj > 0:
                                        # Try to extract array with complete objects
                                        partial_json = truncated_json[:last_complete_obj + 1]
                                        # Close the array
                                        if partial_json.rstrip().endswith('}'):
                                            partial_json = '[' + partial_json + ']'
                                        try:
                                            json_match = json.loads(partial_json)
                                            if isinstance(json_match, list) and len(json_match) > 0:
                                                # Pad to match batch size
                                                while len(json_match) < len(ingredients):
                                                    json_match.append({})
                                                if len(json_match) > len(ingredients):
                                                    json_match = json_match[:len(ingredients)]
                                                return json_match
                                        except:
                                            pass
                                except:
                                    pass
                            
                            # If we can't recover, return empty results for this batch
                            print(f"JSON parse error (truncated response?): {str(e)}")
                            return [{}] * len(ingredients)
                    
                elif response.status == 429:
                    print(f"Rate limit hit for {model_config['name']}, trying next model...")
                    continue  # Try next model
                elif response.status == 403:
                    print(f"Access denied for {model_config['name']} (403), trying next model...")
                    continue  # Skip this model, try next
                elif response.status == 401:
                    raise Exception("Invalid API key")
                else:
                    try:
                        error_data = await response.json()
                        error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                    except:
                        error_msg = f"HTTP {response.status}"
                    print(f"API error ({response.status}): {error_msg}")
        except Exception as e:
            print(f"Exception with {model_config['name']}: {str(e)}")
            continue
    
    return [{}] * len(ingredients)  # Return empty results if all fail

async def process_ingredient_batch(ingredients: List[Dict[str, Any]]) -> Tuple[int, str]:
    """Process a batch of ingredients and update MongoDB - handles ALL missing values
    Returns: (number of ingredients successfully enhanced, last enhanced ingredient name)"""
    
    enhanced_count = 0
    last_enhanced_name = ""
    async with aiohttp.ClientSession() as session:
        results = await enhance_ingredient_batch(session, ingredients)
        
        if not results:
            print(f"Warning: No results returned from API for batch of {len(ingredients)} ingredients")
            return (0, "")
        
        # Update each ingredient in MongoDB
        # Handle case where results array might be shorter than ingredients array
        for idx, ingredient in enumerate(ingredients):
            ingredient_name = ingredient.get("ingredient_name", "Unknown")
            
            # Get result for this ingredient (handle mismatched array lengths)
            if idx < len(results):
                result = results[idx]
            else:
                result = {}
            
            if not result or result.get("error"):
                if not result:
                    print(f"  ⚠️  Skipped: {ingredient_name} (no API result - batch may be incomplete)")
                else:
                    print(f"  ⚠️  Skipped: {ingredient_name} (error: {result.get('error', 'unknown')})")
                continue
            
            update_doc = {}
            extra_data = ingredient.get("extra_data", {}).copy()
            
            # 1. Update enhanced description
            if result.get("description"):
                update_doc["enhanced_description"] = result["description"]
                print(f"  ✓ Processing: {ingredient_name}")
            
            # 2. Update category if needed (default to Active for SpecialChem actives)
            if "category" in result:
                update_doc["category_decided"] = result["category"]
            elif not ingredient.get("category_decided"):
                update_doc["category_decided"] = "Active"
            
            # 3. Update INCI names - create/get INCI objects and link them
            existing_inci_ids = ingredient.get("inci_ids", [])
            extracted_inci = result.get("inci_names", [])
            
            # Fill missing INCI names if ingredient is missing them
            needs_inci = not existing_inci_ids or not ingredient.get("original_inci_name", "").strip()
            
            if extracted_inci:
                # Get or create INCI objects for new INCI names
                new_inci_ids = []
                for inci_name in extracted_inci:
                    if inci_name and inci_name.strip():
                        inci_id = await get_or_create_inci(inci_name.strip())
                        if inci_id and inci_id not in existing_inci_ids:
                            new_inci_ids.append(inci_id)
                
                # Merge with existing INCI IDs
                combined_inci_ids = list(set(existing_inci_ids + new_inci_ids))
                if combined_inci_ids != existing_inci_ids:
                    update_doc["inci_ids"] = combined_inci_ids
                
                # Update original_inci_name if missing
                if not ingredient.get("original_inci_name", "").strip():
                    update_doc["original_inci_name"] = " | ".join(extracted_inci[:3])
            elif needs_inci:
                # API didn't return INCI names but ingredient needs them - try to extract from description
                description = ingredient.get("description", "") or ingredient.get("enhanced_description", "")
                if description:
                    # Simple extraction: look for common INCI patterns in description
                    # This is a fallback - the API should have provided them
                    print(f"  ⚠️  Missing INCI for {ingredient_name} (API didn't return)")
            
            # 4. Update functional categories (functions)
            extracted_functions = result.get("functions", []) or result.get("functional_categories", [])
            existing_func_cat_ids = ingredient.get("functional_category_ids", [])
            needs_categories = not existing_func_cat_ids or not ingredient.get("functionality_category_tree")
            
            if extracted_functions:
                new_func_cat_ids = []
                
                for func_name in extracted_functions:
                    if func_name and func_name.strip():
                        func_id = await get_or_create_func_category(func_name.strip())
                        if func_id and func_id not in existing_func_cat_ids:
                            new_func_cat_ids.append(func_id)
                
                # Merge with existing functional category IDs
                combined_func_ids = list(set(existing_func_cat_ids + new_func_cat_ids))
                if combined_func_ids != existing_func_cat_ids:
                    update_doc["functional_category_ids"] = combined_func_ids
                    
                    # Also update functionality_category_tree format
                    func_cat_tree = [[func_name] for func_name in extracted_functions[:10]]
                    update_doc["functionality_category_tree"] = func_cat_tree
            elif needs_categories:
                print(f"  ⚠️  Missing categories for {ingredient_name} (API didn't return)")
            
            # 5. Update compliance (fill if missing)
            existing_comp = extra_data.get("compliance", [])
            needs_compliance = not existing_comp
            
            if result.get("compliance"):
                normalized_comp = [normalize_text(comp) for comp in result["compliance"]]
                normalized_existing = [normalize_text(comp) for comp in existing_comp]
                new_comp = [
                    comp for comp in result["compliance"]
                    if normalize_text(comp) not in normalized_existing
                ]
                if new_comp:
                    extra_data["compliance"] = existing_comp + new_comp
            elif needs_compliance:
                # Missing compliance but API didn't return - will be filled if API provides next time
                pass
            
            # 6. Update applications (fill if missing)
            existing_apps = extra_data.get("applications", [])
            needs_applications = not existing_apps
            
            if result.get("applications"):
                result_apps = result.get("applications", [])
                normalized_apps = [normalize_text(app) for app in result_apps]
                normalized_existing = [normalize_text(app) for app in existing_apps]
                new_apps = [
                    app for app in result_apps
                    if normalize_text(app) not in normalized_existing
                ]
                if new_apps:
                    extra_data["applications"] = existing_apps + new_apps
            elif needs_applications:
                # Missing applications but API didn't return - will be filled if API provides next time
                pass
            
            # 7. Update properties (fill if missing)
            existing_props = extra_data.get("properties", [])
            needs_properties = not existing_props
            
            if result.get("properties"):
                existing_prop_names = {prop.get("properties", "") or prop.get("name", "") for prop in existing_props}
                
                new_properties = []
                for prop in result["properties"]:
                    # Handle both formats: {"name": "...", "value": "..."} and {"properties": "...", "value_unit": "..."}
                    prop_name = prop.get("name") or prop.get("properties", "")
                    if prop_name and prop_name not in existing_prop_names:
                        normalized_prop = {
                            "properties": normalize_text(prop_name),
                            "value_unit": prop.get("value") or prop.get("value_unit", ""),
                            "test_condition": prop.get("test_condition", ""),
                            "test_method": prop.get("test_method", "")
                        }
                        new_properties.append(normalized_prop)
                        existing_prop_names.add(prop_name)
                
                if new_properties:
                    extra_data["properties"] = existing_props + new_properties
            elif needs_properties:
                # Missing properties but API didn't return - will be filled if API provides next time
                pass
            
            # Update extra_data if any changes
            if extra_data != ingredient.get("extra_data", {}):
                update_doc["extra_data"] = extra_data
            
            # Update in MongoDB
            if update_doc:
                await collection.update_one(
                    {"_id": ingredient["_id"]},
                    {"$set": update_doc}
                )
                if update_doc.get("enhanced_description"):
                    enhanced_count += 1
                    last_enhanced_name = ingredient_name[:40]  # Truncate long names
                    print(f"  ✅ Enhanced: {ingredient_name}")
                else:
                    print(f"  ℹ️  Updated (no description): {ingredient_name}")
    
    return (enhanced_count, last_enhanced_name)

async def main():
    """Main function to enhance SpecialChem ingredients from MongoDB"""
    
    print("=" * 80)
    print("Enhance SpecialChem Ingredients from MongoDB")
    print("=" * 80)
    print(f"Database: {DB_NAME}")
    print(f"Collection: ingre_branded_ingredients")
    print()
    
    # Query: Only SpecialChem Active ingredients missing enhanced_description
    # (The script will also fill missing INCI names, categories, compliance, applications, properties)
    query = {
        "category_decided": "Active",
        "enhanced_description": {"$exists": False},  # Only process ingredients missing enhanced_description
        "extra_data.source": "specialchem"  # Only SpecialChem data
    }
    
    total = await collection.count_documents(query)
    already_enhanced = await collection.count_documents({
        "category_decided": "Active",
        "enhanced_description": {"$exists": True},
        "extra_data.source": "specialchem"
    })
    
    print(f"SpecialChem Active ingredients:")
    print(f"  Total: {total + already_enhanced}")
    print(f"  Already enhanced: {already_enhanced}")
    print(f"  Need enhancement: {total}")
    print()
    
    if total == 0:
        print("All SpecialChem Active ingredients already have enhanced descriptions!")
        return
    
    # Process in batches - SEQUENTIAL (no parallel processing)
    # Batch size with higher max_tokens (8000) to process more per API call
    batch_size = 25
    processed = 0
    enhanced = 0
    failed = 0
    start_time = time.time()
    
    print(f"Processing in batches of {batch_size} (sequential)...")
    print()
    
    # Use cursor to process in batches sequentially
    cursor = collection.find(query)
    
    # Create progress bar
    pbar = tqdm(total=total, desc="Enhancing", unit="ingredients", 
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                position=0, leave=True)
    
    batch_list = []
    batch_num = 0
    async for doc in cursor:
        batch_list.append(doc)
        
        if len(batch_list) >= batch_size:
            batch_num += 1
            print(f"\n📦 Batch {batch_num} ({len(batch_list)} ingredients):")
            try:
                enhanced_in_batch, last_name = await process_ingredient_batch(batch_list)
                processed += len(batch_list)
                enhanced += enhanced_in_batch
                failed_in_batch = len(batch_list) - enhanced_in_batch
                failed += failed_in_batch
                
                # Update progress bar
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                remaining_time = (total - processed) / rate if rate > 0 else 0
                
                pbar.update(len(batch_list))
                pbar.set_postfix({
                    'Enhanced': enhanced,
                    'Failed': failed,
                    'Rate': f"{rate:.1f}/s",
                    'ETA': f"{int(remaining_time//60)}m{int(remaining_time%60)}s" if remaining_time > 0 else "?",
                    'Last': last_name if last_name else "N/A"
                })
                print(f"  📊 Batch {batch_num} complete: {enhanced_in_batch}/{len(batch_list)} enhanced")
            except Exception as e:
                print(f"\n❌ Error processing batch {batch_num}: {str(e)}")
                failed += len(batch_list)
                processed += len(batch_list)
                pbar.update(len(batch_list))
            
            batch_list = []
    
    # Process remaining
    if batch_list:
        batch_num += 1
        print(f"\n📦 Final batch ({len(batch_list)} ingredients):")
        try:
            enhanced_in_batch, last_name = await process_ingredient_batch(batch_list)
            processed += len(batch_list)
            enhanced += enhanced_in_batch
            failed += len(batch_list) - enhanced_in_batch
            pbar.update(len(batch_list))
            pbar.set_postfix({'Last': last_name if last_name else "N/A"})
            print(f"  📊 Final batch complete: {enhanced_in_batch}/{len(batch_list)} enhanced")
        except Exception as e:
            print(f"\n❌ Error processing final batch: {str(e)}")
            failed += len(batch_list)
            processed += len(batch_list)
            pbar.update(len(batch_list))
    
    pbar.close()
    
    print()
    print("=" * 80)
    print("Enhancement Complete!")
    total_time = time.time() - start_time
    print(f"  Processed: {processed}/{total} ingredients")
    print(f"  Enhanced: {enhanced} ingredients ({enhanced/processed*100:.1f}% success rate)" if processed > 0 else "  Enhanced: 0")
    print(f"  Failed: {failed} ingredients")
    print(f"  Total time: {int(total_time//60)}m {int(total_time%60)}s")
    print(f"  Average rate: {processed/total_time:.1f} ingredients/second" if total_time > 0 else "  Average rate: N/A")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())

