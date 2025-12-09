# app/ai_ingredient_intelligence/scripts/clean_external_products.py
"""
Script to clean the externalProducts collection by extracting only the INCI list
from the ingredients field using AI.

This script:
1. Connects to MongoDB and queries externalProducts collection
2. Skips products that have already been cleaned (ingredientsCleaned: true)
3. Uses AI (GPT-5) to extract only the INCI list from ingredients field
4. Updates the document with cleaned ingredients and marks it as cleaned

Usage:
    python -m app.ai_ingredient_intelligence.scripts.clean_external_products
"""

import os
import json
import asyncio
import aiohttp
import time
from collections import defaultdict
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm
from typing import Optional, Dict, Any, List

# Load .env variables
load_dotenv()

# MongoDB Configuration
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin")
DB_NAME: str = os.getenv("DB_NAME", "skin_bb")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY") or ""

if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY is missing. Please set it in your .env file.")

OPENAI_API_URL: str = "https://api.openai.com/v1/chat/completions"

# Mongo client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
# Collection will be determined in main() to handle case sensitivity
collection = None

# Rate limiter to track requests per minute
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
    
    async def wait_if_needed(self, model_name: str, rpm_limit: int):
        """Wait if we're approaching the rate limit for a model"""
        current_time = time.time()
        minute_ago = current_time - 60
        
        # Clean old requests
        self.requests[model_name] = [req_time for req_time in self.requests[model_name] if req_time > minute_ago]
        
        # Check if we need to wait (use 80% of limit for better utilization)
        aggressive_limit = int(rpm_limit * 0.8)
        if len(self.requests[model_name]) >= aggressive_limit:
            oldest_request = min(self.requests[model_name])
            wait_time = 60 - (current_time - oldest_request) + 1
            if wait_time > 0:
                print(f"⏱️ Rate limit approaching for {model_name}, waiting {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
        
        # Record this request
        self.requests[model_name].append(current_time)

# Global rate limiter
rate_limiter = RateLimiter()


async def clean_ingredients_with_ai(
    session: aiohttp.ClientSession,
    ingredients_text: str
) -> Optional[List[str]]:
    """
    Use AI to extract only the INCI list from ingredients text.
    Returns a list of cleaned ingredient names, or None if extraction fails.
    """
    if not ingredients_text or not ingredients_text.strip():
        return None
    
    prompt = f"""You are a cosmetic ingredient expert. Extract ONLY the INCI (International Nomenclature of Cosmetic Ingredients) list from the following text.

Remove all unnecessary text, descriptions, headers, footers, and other non-ingredient content. Return ONLY the clean INCI ingredient list.

Input text:
{ingredients_text}

CRITICAL INSTRUCTIONS:
1. Extract ONLY the actual INCI ingredient names
2. Remove all headers like "Ingredients:", "Full Ingredients List:", "INGREDIENTS", etc.
3. Remove all descriptions, explanations, or additional text
4. Remove any marketing text or product information
5. Return ingredients as a comma-separated list
6. Each ingredient should be properly formatted (e.g., "Water", "Glycerin", "Sodium Hyaluronate")
7. Preserve ingredient combinations that use "(and)" or "&" (e.g., "Xylitylglucoside (and) Anhydroxylitol")
8. Do NOT include any explanations, just the ingredient list

Output format: Return ONLY a comma-separated list of ingredients, nothing else.
Example output: Water, Glycerin, Sodium Hyaluronate, Niacinamide, Xylitylglucoside (and) Anhydroxylitol

If you cannot extract a valid INCI list, return: "UNABLE_TO_EXTRACT"
"""

    # Model priority - GPT-5 first (user preference)
    models_to_try = [
        # GPT-5 models (user preference)
        {"name": "gpt-5", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-chat-latest", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-mini", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-mini-2025-08-07", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        
        # GPT-4 models as fallback
        {"name": "chatgpt-4o-latest", "max_tokens": 2000, "endpoint": "chat", "rpm": 200, "tpm": 500000},
        {"name": "gpt-4.1", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4o-2024-11-20", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4o", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        
        # Fast models as last resort
        {"name": "gpt-3.5-turbo", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-3.5-turbo-instruct", "max_tokens": 2000, "endpoint": "completions", "rpm": 3500, "tpm": 90000},
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        endpoint = model_config["endpoint"]
        rpm_limit = model_config["rpm"]
        
        # Check rate limits before making request
        await rate_limiter.wait_if_needed(model_name, rpm_limit)
        
        # Small delay between requests
        await asyncio.sleep(0.5)
        
        # Prepare payload based on endpoint type
        if endpoint == "chat":
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}]
            }
            # GPT-5 models use max_completion_tokens
            if model_name.startswith("gpt-5"):
                payload["max_completion_tokens"] = max_tokens
            else:
                payload["max_tokens"] = max_tokens
        else:  # completions endpoint
            payload = {
                "model": model_name,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "top_p": 0.9
            }
        
        try:
            # Use correct endpoint based on model type
            api_url = "https://api.openai.com/v1/chat/completions" if endpoint == "chat" else "https://api.openai.com/v1/completions"
            
            async with session.post(
                api_url,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if endpoint == "chat":
                        content = data["choices"][0]["message"]["content"].strip()
                    else:
                        content = data["choices"][0]["text"].strip()
                    
                    # Check if extraction failed
                    if "UNABLE_TO_EXTRACT" in content.upper():
                        print(f"  ⚠️ AI could not extract ingredients")
                        return None
                    
                    # Parse the comma-separated list
                    from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
                    cleaned_ingredients = parse_inci_string(content)
                    
                    if cleaned_ingredients:
                        return cleaned_ingredients
                    else:
                        print(f"  ⚠️ No ingredients found in AI response")
                        continue
                        
                elif response.status == 429:
                    # Rate limited, try next model
                    print(f"  ⚠️ Rate limited on {model_name}, trying next model...")
                    continue
                else:
                    error_text = await response.text()
                    print(f"  ⚠️ Error {response.status} on {model_name}: {error_text[:100]}")
                    continue
                    
        except asyncio.TimeoutError:
            print(f"  ⚠️ Timeout on {model_name}, trying next model...")
            continue
        except Exception as e:
            print(f"  ⚠️ Exception on {model_name}: {type(e).__name__}: {str(e)[:100]}")
            continue
    
    # All models failed
    print(f"  ❌ All models failed to extract ingredients")
    return None


async def process_product(
    session: aiohttp.ClientSession,
    product: Dict[str, Any],
    stats: Dict[str, int],
    collection
) -> bool:
    """
    Process a single product: clean ingredients and update database.
    Returns True if successful, False otherwise.
    """
    product_id = product.get("_id")
    product_name = product.get("productName") or product.get("name") or "Unknown"
    ingredients_raw = product.get("ingredients", "")
    
    # Handle both string and array formats
    if isinstance(ingredients_raw, list):
        # If it's already an array, join it to a string for AI processing
        ingredients_raw = ", ".join(str(ing) for ing in ingredients_raw if ing)
    
    if not ingredients_raw or not isinstance(ingredients_raw, str) or not ingredients_raw.strip():
        stats["skipped_no_ingredients"] += 1
        return False
    
    # Skip if already cleaned
    if product.get("ingredientsCleaned") is True:
        stats["skipped_already_cleaned"] += 1
        return False
    
    # Extract ingredients using AI
    cleaned_ingredients = await clean_ingredients_with_ai(session, ingredients_raw)
    
    if not cleaned_ingredients:
        stats["failed_extraction"] += 1
        return False
    
    # Update the document
    try:
        await collection.update_one(
            {"_id": product_id},
            {
                "$set": {
                    "ingredients": cleaned_ingredients,  # Store as array for better structure
                    "ingredientsCleaned": True,
                    "ingredientsCleanedAt": time.time()
                }
            }
        )
        stats["success"] += 1
        print(f"  ✅ Cleaned: {product_name[:50]} ({len(cleaned_ingredients)} ingredients)")
        return True
    except Exception as e:
        print(f"  ❌ Database update failed for {product_name[:50]}: {str(e)}")
        stats["failed_update"] += 1
        return False


async def process_batch(
    session: aiohttp.ClientSession,
    products: List[Dict[str, Any]],
    stats: Dict[str, int],
    batch_num: int,
    collection
):
    """Process a batch of products concurrently"""
    print(f"\n📦 Processing batch {batch_num} ({len(products)} products)...")
    
    tasks = [process_product(session, product, stats, collection) for product in products]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Count exceptions
    for result in results:
        if isinstance(result, Exception):
            stats["errors"] += 1
            print(f"  ❌ Exception in batch: {type(result).__name__}: {str(result)[:100]}")


async def main():
    """Main function to clean externalProducts collection"""
    print("🧹 Starting externalProducts cleaning script...")
    print(f"📊 Database: {DB_NAME}")
    
    # Try to find the correct collection name
    collection_names = await db.list_collection_names()
    target_collection = None
    collection_name = None
    for name in collection_names:
        if name.lower() == "externalproducts":
            target_collection = db[name]
            collection_name = name
            print(f"📦 Collection: {name} (found)")
            break
    
    if target_collection is None:
        print(f"❌ Collection 'externalproducts' not found!")
        print(f"Available collections: {', '.join(collection_names[:20])}")
        return
    
    collection = target_collection
    print()
    
    # First, get diagnostic information
    print("🔍 Gathering diagnostic information...")
    total_count = await collection.count_documents({})
    has_ingredients_count = await collection.count_documents({
        "ingredients": {"$exists": True, "$ne": None, "$ne": ""}
    })
    already_cleaned_count = await collection.count_documents({
        "ingredientsCleaned": True
    })
    
    # Check for array vs string ingredients
    sample_product = await collection.find_one({"ingredients": {"$exists": True}})
    if sample_product:
        ingredients_type = type(sample_product.get("ingredients")).__name__
        print(f"   Sample ingredients type: {ingredients_type}")
        if isinstance(sample_product.get("ingredients"), str):
            sample_preview = sample_product.get("ingredients", "")[:100]
            print(f"   Sample preview: {sample_preview}...")
    
    print(f"📊 Collection Statistics:")
    print(f"   Total products: {total_count}")
    print(f"   Products with ingredients: {has_ingredients_count}")
    print(f"   Products already cleaned: {already_cleaned_count}")
    print()
    
    # Statistics
    stats = {
        "total": 0,
        "skipped_already_cleaned": 0,
        "skipped_no_ingredients": 0,
        "success": 0,
        "failed_extraction": 0,
        "failed_update": 0,
        "errors": 0
    }
    
    # Query products that need cleaning
    # Skip products that are already cleaned
    query = {
        "ingredients": {"$exists": True, "$ne": None, "$ne": ""},
        "$or": [
            {"ingredientsCleaned": {"$ne": True}},
            {"ingredientsCleaned": {"$exists": False}}
        ]
    }
    
    print("🔍 Querying products that need cleaning...")
    products_cursor = collection.find(query)
    all_products = await products_cursor.to_list(length=None)
    stats["total"] = len(all_products)
    
    print(f"📊 Found {stats['total']} products to process")
    print(f"   (Skipping products with ingredientsCleaned: true)")
    print()
    
    if stats["total"] == 0:
        print("⚠️  No products found to clean!")
        print()
        print("Possible reasons:")
        print("   1. All products are already marked as cleaned")
        print("   2. No products have an 'ingredients' field")
        print("   3. All ingredients fields are empty/null")
        print()
        print("💡 To re-clean all products, you can manually remove the 'ingredientsCleaned' flag")
        print("   or modify the query in the script.")
        return
    
    # Process products in batches
    batch_size = 5  # Process 5 products concurrently
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(all_products), batch_size):
            batch = all_products[i:i + batch_size]
            await process_batch(session, batch, stats, (i // batch_size) + 1, collection)
            
            # Small delay between batches
            if i + batch_size < len(all_products):
                await asyncio.sleep(2)
    
    # Print final statistics
    print("\n" + "="*60)
    print("📊 FINAL STATISTICS")
    print("="*60)
    print(f"Total products found: {stats['total']}")
    print(f"✅ Successfully cleaned: {stats['success']}")
    print(f"⏭️  Skipped (already cleaned): {stats['skipped_already_cleaned']}")
    print(f"⏭️  Skipped (no ingredients): {stats['skipped_no_ingredients']}")
    print(f"❌ Failed (extraction): {stats['failed_extraction']}")
    print(f"❌ Failed (update): {stats['failed_update']}")
    print(f"❌ Errors: {stats['errors']}")
    print("="*60)
    
    # Close database connection
    client.close()
    print("\n✅ Script completed!")


if __name__ == "__main__":
    asyncio.run(main())

