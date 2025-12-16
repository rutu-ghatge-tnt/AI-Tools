# app/ai_ingredient_intelligence/scripts/clean_external_products.py
"""
Script to clean the externalproducts collection by extracting only the INCI list
from the ingredients field using Claude AI.

This script:
1. Connects to MongoDB and queries externalproducts collection
2. Skips products that have already been cleaned (ingredientsCleaned: true)
3. Uses Claude AI to extract only the INCI list from ingredients field
4. Updates the document with cleaned ingredients and marks it as cleaned

Usage:
    python -m app.ai_ingredient_intelligence.scripts.clean_external_products

Requirements:
    - CLAUDE_API_KEY must be set in .env file
    - anthropic package must be installed (pip install anthropic)
"""

import os
import json
import asyncio
import time
from collections import defaultdict
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional, Dict, Any, List

# Try to import anthropic
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("Warning: anthropic package not installed. Install with: pip install anthropic")

# Load .env variables
load_dotenv()

# MongoDB Configuration
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin")
DB_NAME: str = os.getenv("DB_NAME", "skin_bb")
CLAUDE_API_KEY: str = os.getenv("CLAUDE_API_KEY") or ""

if not CLAUDE_API_KEY:
    raise RuntimeError("❌ CLAUDE_API_KEY is missing. Please set it in your .env file.")

if not ANTHROPIC_AVAILABLE:
    raise RuntimeError("❌ anthropic package is not installed. Install with: pip install anthropic")

# Initialize Claude client
claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

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
    ingredients_text: str
) -> Optional[List[str]]:
    """
    Use AI to extract only the INCI list from ingredients text.
    Returns a list of cleaned ingredient names, or None if extraction fails.
    """
    if not ingredients_text or not ingredients_text.strip():
        return None
    
    # Truncate if too long (Claude has token limits)
    ingredients_text_truncated = ingredients_text[:5000] if len(ingredients_text) > 5000 else ingredients_text
    
    # Check if input is already a clean comma-separated list (common case)
    # If it looks like a clean list, try parsing it directly first
    if "," in ingredients_text_truncated and len(ingredients_text_truncated) < 2000:
        # Check if it looks like a clean list (has commas, no obvious headers/descriptions)
        has_headers = any(marker in ingredients_text_truncated.lower() for marker in [
            "full ingredients", "ingredients list", "ingredients:", "expiry date",
            "country of origin", "manufacturer", "importer", "address:"
        ])
        
        if not has_headers:
            # Try parsing directly - might already be clean
            from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
            direct_parse = parse_inci_string(ingredients_text_truncated)
            if direct_parse and len(direct_parse) >= 2:  # If we get 2+ ingredients, it's probably clean
                print(f"  ✅ Input appears to be clean list, parsed directly ({len(direct_parse)} ingredients)")
                return direct_parse
    
    prompt = f"""Extract the INCI ingredient list from this text. Return ONLY a comma-separated list of ingredient names.

Text:
{ingredients_text_truncated}

Rules:
- Extract only INCI ingredient names
- Remove headers, descriptions, marketing text, expiry dates, addresses
- Keep combinations with "(and)" or "&" intact
- Return format: "Ingredient1, Ingredient2, Ingredient3"
- No explanations, just the list

If the text is already a clean ingredient list, return it exactly as-is.
If you cannot find any ingredients, return: UNABLE_TO_EXTRACT

Example output: Water, Glycerin, Sodium Hyaluronate, Niacinamide, Xylitylglucoside (and) Anhydroxylitol
"""

    # Claude models to try (in order of preference)
    # First try the model from environment variable, then fallbacks
    primary_model = os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929"
    
    models_to_try = [
        {"name": primary_model, "max_tokens": 8192},
        {"name": "claude-sonnet-4-5-20250929", "max_tokens": 8192},  # Claude Sonnet 4.5
        {"name": "claude-3-5-haiku-20241022", "max_tokens": 8192},  # Fast fallback (this one works)
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        
        # Check rate limits before making request (Claude has different limits)
        await rate_limiter.wait_if_needed(model_name, 50)  # Conservative rate limit
        
        # Small delay between requests
        await asyncio.sleep(0.5)
        
        try:
            # Use Claude API (run in thread pool since it's synchronous)
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: claude_client.messages.create(
                        model=model_name,
                        max_tokens=max_tokens,
                        temperature=0.3,
                        messages=[
                            {"role": "user", "content": prompt}
                        ]
                    )
                ),
                timeout=30.0  # 30 second timeout
            )
            
            content = response.content[0].text.strip()
            
            # Debug: Show first 200 chars of response for troubleshooting
            if len(content) > 200:
                debug_content = content[:200] + "..."
            else:
                debug_content = content
            
            # Check if extraction failed
            if "UNABLE_TO_EXTRACT" in content.upper():
                print(f"  ⚠️ AI returned UNABLE_TO_EXTRACT from {model_name}")
                print(f"     Input preview: {ingredients_text_truncated[:150]}...")
                print(f"     Response: {debug_content}")
                # If it's the last model, show more details
                if model_config == models_to_try[-1]:
                    print(f"     Full input length: {len(ingredients_text_truncated)} chars")
                continue  # Try next model
            
            # Parse the comma-separated list
            from app.ai_ingredient_intelligence.utils.inci_parser import parse_inci_string
            cleaned_ingredients = parse_inci_string(content)
            
            if cleaned_ingredients and len(cleaned_ingredients) > 0:
                print(f"  ✅ Successfully extracted {len(cleaned_ingredients)} ingredients using {model_name}")
                return cleaned_ingredients
            else:
                print(f"  ⚠️ No ingredients found in AI response from {model_name}")
                print(f"     Response preview: {debug_content}")
                continue
                    
        except asyncio.TimeoutError:
            print(f"  ⚠️ Timeout on {model_name}, trying next model...")
            continue
        except asyncio.CancelledError:
            print(f"  ⚠️ Request cancelled on {model_name}, trying next model...")
            continue
        except Exception as e:
            error_msg = str(e)
            # Check if it's a rate limit error
            if "rate limit" in error_msg.lower() or "429" in error_msg:
                print(f"  ⚠️ Rate limited on {model_name}, trying next model...")
                await asyncio.sleep(2)  # Wait a bit longer for rate limits
                continue
            else:
                print(f"  ⚠️ Exception on {model_name}: {type(e).__name__}: {str(e)[:100]}")
                continue
    
    # All models failed
    print(f"  ❌ All models failed to extract ingredients")
    return None


async def process_product(
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
    
    # Skip if already cleaned
    if product.get("ingredientsCleaned") is True:
        stats["skipped_already_cleaned"] += 1
        return False
    
    # If ingredients are already a clean array, use them directly
    if isinstance(ingredients_raw, list):
        # Check if it's already a clean list of strings
        if all(isinstance(ing, str) and ing.strip() for ing in ingredients_raw):
            # Already clean array - just update the flag
            try:
                await collection.update_one(
                    {"_id": product_id},
                    {
                        "$set": {
                            "ingredients": ingredients_raw,  # Keep as array
                            "ingredientsCleaned": True,
                            "ingredientsCleanedAt": time.time()
                        }
                    }
                )
                stats["success"] += 1
                print(f"  ✅ Already clean array: {product_name[:50]} ({len(ingredients_raw)} ingredients)")
                return True
            except Exception as e:
                print(f"  ❌ Database update failed for {product_name[:50]}: {str(e)}")
                stats["failed_update"] += 1
                return False
        else:
            # Array but needs cleaning - join for AI processing
            ingredients_raw = ", ".join(str(ing) for ing in ingredients_raw if ing)
    
    if not ingredients_raw or not isinstance(ingredients_raw, str) or not ingredients_raw.strip():
        stats["skipped_no_ingredients"] += 1
        return False
    
    # Extract ingredients using AI
    cleaned_ingredients = await clean_ingredients_with_ai(ingredients_raw)
    
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
    products: List[Dict[str, Any]],
    stats: Dict[str, int],
    batch_num: int,
    collection
):
    """Process a batch of products concurrently"""
    print(f"\n📦 Processing batch {batch_num} ({len(products)} products)...")
    
    tasks = [process_product(product, stats, collection) for product in products]
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
    for i in range(0, len(all_products), batch_size):
        batch = all_products[i:i + batch_size]
        await process_batch(batch, stats, (i // batch_size) + 1, collection)
        
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

