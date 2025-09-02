# app/ai_ingredient_intelligence/scripts/enrich_description.py
"""Script to enrich ingredient descriptions using LLM"""

import os
import json
import random
import asyncio
import aiohttp
import time
from collections import defaultdict
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm
from typing import Optional, Dict, Any

# Load .env variables
load_dotenv()

# ✅ Read env vars correctly with defaults (DB_NAME fixed to skin_bb)
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin")
DB_NAME: str = os.getenv("DB_NAME", "skin_bb")   # 👈 match Compass
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY") or ""

if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY is missing. Please set it in your .env file.")

OPENAI_API_URL: str = "https://api.openai.com/v1/chat/completions"

# Mongo client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db["ingre_branded_ingredients"]

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
        
        # Check if we need to wait (be very conservative - use 50% of limit)
        conservative_limit = int(rpm_limit * 0.5)
        if len(self.requests[model_name]) >= conservative_limit:
            oldest_request = min(self.requests[model_name])
            wait_time = 60 - (current_time - oldest_request) + 5  # Add 5 second buffer
            if wait_time > 0:
                print(f"⏱️ Rate limit approaching for {model_name}, waiting {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
        
        # Record this request
        self.requests[model_name].append(current_time)

# Global rate limiter
rate_limiter = RateLimiter()


# ------------------ Model Information ------------------ #
def show_available_models():
    """Display information about available models and their capabilities"""
    print("🤖 Available Models (tries each until one succeeds):")
    print("   • gpt-5: Primary model (500 RPM, 30K TPM, highest quality)")
    print("   • chatgpt-4o-latest: Latest ChatGPT-4o (200 RPM, 500K TPM, high quality)")
    print("   • gpt-4.1: Stable GPT-4 (500 RPM, 30K TPM, consistent performance)")
    print("   • gpt-5-mini-2025-08-07: GPT-5 Mini variant (500 RPM, 200K TPM)")
    print("   • gpt-5-mini: Compact GPT-5 (500 RPM, 200K TPM, best balance)")
    print("   • gpt-5-chat-latest: Latest GPT-5 variant (500 RPM, 30K TPM)")
    print("   • gpt-3.5-turbo-instruct: Fastest model (3500 RPM, 90K TPM, completions endpoint)")
    print("   • gpt-4o-2024-11-20: GPT-4o variant (500 RPM, 30K TPM)")
    print("   • gpt-3.5-turbo: Fast model (3500 RPM, 90K TPM)")
    print("   • gpt-5-nano: Nano GPT-5 (500 RPM, 200K TPM)")
    print("   • gpt-5-2025-08-07: GPT-5 variant (500 RPM, 30K TPM)")
    print("   • gpt-4o: Standard GPT-4o (500 RPM, 30K TPM)")
    print("   • Only saves proper enhanced descriptions - no fallback error messages")
    print()

# ------------------ Cleanup Functions ------------------ #
async def cleanup_basic_descriptions():
    """Remove all enhanced descriptions starting with 'Basic' word from entire collection"""
    print("🧹 Cleaning up existing 'Basic' descriptions from entire collection...")
    
    # 🔹 First, get total count of all documents
    total_docs = await collection.count_documents({})
    print(f"📊 Total documents in collection: {total_docs}")
    
    # 🔹 Find documents with enhanced_description starting with "Basic" (case insensitive)
    query = {"enhanced_description": {"$regex": "^Basic", "$options": "i"}}
    basic_count = await collection.count_documents(query)
    
    if basic_count > 0:
        print(f"🔍 Found {basic_count} documents with 'Basic' descriptions")
        
        # 🔹 Show some examples of what will be removed
        print("📝 Examples of 'Basic' descriptions found:")
        cursor = collection.find(query).limit(5)
        async for doc in cursor:
            ingredient_name = doc.get("ingredient_name", "Unknown")
            enhanced_desc = doc.get("enhanced_description", "")[:100] + "..." if len(doc.get("enhanced_description", "")) > 100 else doc.get("enhanced_description", "")
            print(f"   • {ingredient_name}: {enhanced_desc}")
        
        # 🔹 Remove the enhanced_description and category_decided fields for these documents
        result = await collection.update_many(
            query,
            {"$unset": {"enhanced_description": "", "category_decided": ""}}
        )
        
        print(f"✅ Successfully removed 'Basic' descriptions from {result.modified_count} documents")
        print(f"🔄 These ingredients will be reprocessed in the next run")
        
        # 🔹 Verify cleanup
        remaining_basic = await collection.count_documents(query)
        if remaining_basic == 0:
            print("✅ Verification: All 'Basic' descriptions have been removed!")
        else:
            print(f"⚠️ Warning: {remaining_basic} 'Basic' descriptions still remain")
            
    else:
        print("✅ No 'Basic' descriptions found to clean up")
    
    # 🔹 Show final statistics
    final_total = await collection.count_documents({})
    final_with_enhanced = await collection.count_documents({"enhanced_description": {"$exists": True}})
    final_without_enhanced = await collection.count_documents({"enhanced_description": {"$exists": False}})
    
    print(f"\n📊 Final Collection Status:")
    print(f"   • Total documents: {final_total}")
    print(f"   • With enhanced descriptions: {final_with_enhanced}")
    print(f"   • Without enhanced descriptions: {final_without_enhanced}")
    print(f"   • Ready for reprocessing: {final_without_enhanced}")

async def cleanup_failed_processing_entries():
    """Remove fallback entries created when processing failed"""
    print("🧹 Cleaning up failed processing entries...")
    
    # 🔹 First, get total count of all documents
    total_docs = await collection.count_documents({})
    print(f"📊 Total documents in collection: {total_docs}")
    
    # 🔹 Find documents with "Unknown" category or "Processing failed" descriptions
    query = {
        "$or": [
            {"category_decided": "Unknown"},
            {"category_decided": "Error"},
            {"enhanced_description": {"$regex": "Processing failed", "$options": "i"}},
            {"enhanced_description": {"$regex": "Processing error", "$options": "i"}}
        ]
    }
    
    failed_count = await collection.count_documents(query)
    
    if failed_count > 0:
        print(f"🔍 Found {failed_count} documents with failed processing entries")
        
        # 🔹 Show some examples of what will be removed
        print("📝 Examples of failed processing entries found:")
        cursor = collection.find(query).limit(5)
        async for doc in cursor:
            ingredient_name = doc.get("ingredient_name", "Unknown")
            category = doc.get("category_decided", "N/A")
            enhanced_desc = doc.get("enhanced_description", "")[:100] + "..." if len(doc.get("enhanced_description", "")) > 100 else doc.get("enhanced_description", "")
            print(f"   • {ingredient_name}: Category='{category}', Description='{enhanced_desc}'")
        
        # 🔹 Remove the enhanced_description and category_decided fields for these documents
        result = await collection.update_many(
            query,
            {"$unset": {"enhanced_description": "", "category_decided": ""}}
        )
        
        print(f"✅ Successfully removed failed processing entries from {result.modified_count} documents")
        print(f"🔄 These ingredients will be reprocessed in the next run")
        
        # 🔹 Verify cleanup
        remaining_failed = await collection.count_documents(query)
        if remaining_failed == 0:
            print("✅ Verification: All failed processing entries have been removed!")
        else:
            print(f"⚠️ Warning: {remaining_failed} failed processing entries still remain")
            
    else:
        print("✅ No failed processing entries found to clean up")
    
    # 🔹 Show final statistics
    final_total = await collection.count_documents({})
    final_with_enhanced = await collection.count_documents({"enhanced_description": {"$exists": True}})
    final_without_enhanced = await collection.count_documents({"enhanced_description": {"$exists": False}})
    
    print(f"\n📊 Final Collection Status:")
    print(f"   • Total documents: {final_total}")
    print(f"   • With enhanced descriptions: {final_with_enhanced}")
    print(f"   • Without enhanced descriptions: {final_without_enhanced}")
    print(f"   • Ready for reprocessing: {final_without_enhanced}")

# ------------------ Rate Limit Optimization ------------------ #
def calculate_optimal_batch_size(model_name: str, endpoint: str) -> int:
    """Calculate optimal batch size based on OpenAI rate limits and model capabilities"""
    
    # 🔹 More aggressive batch sizes for faster processing
    if model_name == "gpt-5":
        # GPT-5: 200 RPD, 3 RPM, high TPM
        return 1  # Process one at a time due to low RPM
    elif model_name == "gpt-3.5-turbo-instruct":
        # GPT-3.5-turbo-instruct: 3,500 RPD, 3,500 RPM, high TPM
        return 10  # Increased from 5 to 10 for faster processing
    
    return 1  # Default to 1

# ------------------ OpenAI Call ------------------ #
async def call_openai(session: aiohttp.ClientSession,
                      ingredient_name: Optional[str],
                      description: Optional[str] = None) -> Dict[str, Any]:
    """Call OpenAI API with smart fallback to GPT-5 + GPT-3.5-turbo"""
    
    # 🔹 Clean and sanitize ingredient name
    clean_ingredient = str(ingredient_name or 'Unknown').strip()
    clean_description = str(description or 'No description available').strip()
    
    # 🔹 Enhanced prompt for better JSON output with fallback instructions
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

    # 🔹 Use only models that are accessible (not 403 errors) - you still have quota issues
    models_to_try = [
        # These models are accessible but have quota issues - try them anyway
        {"name": "gpt-3.5-turbo-instruct", "max_tokens": 1000, "endpoint": "completions", "rpm": 3500, "tpm": 90000},
        {"name": "gpt-3.5-turbo", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-chat-latest", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-mini", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-mini-2025-08-07", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-nano", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-2025-08-07", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4.1", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4o", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4o-2024-11-20", "max_tokens": 1000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "chatgpt-4o-latest", "max_tokens": 1000, "endpoint": "chat", "rpm": 200, "tpm": 500000}
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        endpoint = model_config["endpoint"]
        rpm_limit = model_config["rpm"]
        
        print(f"🔄 Trying {model_name} ({endpoint} endpoint)...")
        
        # Check rate limits before making request
        await rate_limiter.wait_if_needed(model_name, rpm_limit)
        
        # Add a much longer delay to avoid hitting daily rate limits
        await asyncio.sleep(10)  # 10 second delay between requests
        
        # 🔹 Prepare payload based on endpoint type
        if endpoint == "chat":
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}]
            }
            # 🔹 Add max_tokens based on model type
            if model_name.startswith("gpt-5"):
                payload["max_completion_tokens"] = max_tokens  # GPT-5 models use max_completion_tokens
            else:
                payload["max_tokens"] = max_tokens  # Other models use max_tokens
        else:  # completions endpoint
            payload = {
                "model": model_name,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "top_p": 0.9
            }
        
        try:
            # 🔹 Use correct endpoint based on model type
            api_url = "https://api.openai.com/v1/chat/completions" if endpoint == "chat" else "https://api.openai.com/v1/completions"
            
            async with session.post(
                api_url,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    # 🔹 Parse response
                    if not data or "choices" not in data:
                        print(f"⚠️ {model_name} returned empty response - trying next model")
                        continue
                    
                    # 🔹 Handle different response formats based on endpoint
                    if endpoint == "chat":
                        content = data["choices"][0]["message"]["content"]
                    else:  # completions endpoint
                        content = data["choices"][0]["text"]
                    
                    if not content or not content.strip():
                        print(f"⚠️ {model_name} returned empty content - trying next model")
                        continue
                    
                    content = content.strip()
                    
                    # 🔹 Try to parse JSON from response
                    try:
                        result = json.loads(content)
                    except json.JSONDecodeError:
                        # 🔹 Try to extract JSON from potential markdown or extra text
                        import re
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            result = json.loads(json_match.group())
                        else:
                            print(f"⚠️ {model_name} returned invalid JSON - trying next model")
                            continue
                    
                    # 🔹 Validate required fields
                    if "category" not in result or "description" not in result:
                        print(f"⚠️ {model_name} missing required fields - trying next model")
                        continue
                    
                    # 🔹 Validate field types
                    if not isinstance(result["category"], str) or not isinstance(result["description"], str):
                        print(f"⚠️ {model_name} invalid field types - trying next model")
                        continue
                    
                    # 🔹 Only accept proper categories (not "Unknown")
                    if result["category"] == "Unknown":
                        print(f"⚠️ {model_name} returned 'Unknown' category - trying next model")
                        continue
                    
                    print(f"✅ {model_name} successful!")
                    return result
                
                elif response.status == 403:
                    # Model not available or access denied
                    error_text = await response.text()
                    print(f"⚠️ {model_name} HTTP 403: {error_text}")
                    print(f"❌ {model_name} not available, trying next model...")
                    continue
                
                elif response.status == 429:
                    # Rate limit - try next model
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "Rate limit")
                    print(f"⚠️ {model_name} rate limit: {error_msg}")
                    
                    # Check if it's a daily limit vs minute limit
                    if "requests per day" in error_msg.lower() or "tokens per day" in error_msg.lower():
                        print(f"📅 {model_name} daily limit reached - trying next model...")
                    else:
                        print(f"⏱️ {model_name} minute limit - trying next model...")
                    continue
                
                else:
                    error_text = await response.text()
                    print(f"⚠️ {model_name} HTTP {response.status}: {error_text} - trying next model...")
                    continue
                    
        except Exception as e:
            print(f"⚠️ {model_name} error: {e} - trying next model...")
            continue
    
    # 🔹 If all models fail, return None (don't save anything)
    print(f"❌ All models failed for {clean_ingredient} - skipping this ingredient")
    return None


# ------------------ Worker ------------------ #
async def process_ingredient(session: aiohttp.ClientSession, ingredient: Dict[str, Any]) -> None:
    name = ingredient.get("ingredient_name", "Unknown Ingredient")
    desc = ingredient.get("description")

    try:
        result = await call_openai(session, name, desc)
        
        # 🔹 Only save if we got a proper result
        if result and "category" in result and "description" in result:
            await collection.update_one(
                {"_id": ingredient["_id"]},
                {"$set": {
                    "category_decided": result["category"],
                    "enhanced_description": result["description"]
                }}
            )
            print(f"💾 Saved enhanced description for {name}")
        else:
            print(f"⏭️ Skipping {name} - no proper result from any model")
                    
    except Exception as e:
        print(f"❌ {name} failed completely: {e}")
        # 🔹 Don't save any fallback data - just skip this ingredient
        print(f"⏭️ Skipping {name} - will be retried in next run")


# ------------------ Main ------------------ #
async def main(batch_size: int = None) -> None:  # GPT-5 only processing
    # 🔹 First, clean up any existing 'Basic' descriptions and failed processing entries
    await cleanup_basic_descriptions()
    await cleanup_failed_processing_entries()
    
    # Process only ingredients that don't have enhanced_description yet
    query: Dict[str, Any] = {"enhanced_description": {"$exists": False}}

    total = await collection.count_documents(query)
    
    # Count already processed ingredients
    already_processed = await collection.count_documents({"enhanced_description": {"$exists": True}})
    
    print(f"🔎 Processing {total} branded ingredients (skipping already enhanced ones)...")
    print(f"✅ Already processed: {already_processed} ingredients")
    print(f"📝 Total in database: {total + already_processed} ingredients")
    print()
    print("Using MONGO_URI:", MONGO_URI)
    print("Connected DB:", db.name)
    print("🚀 Using multiple models - tries each until one succeeds!")
    print("📝 Original descriptions will be preserved, enhanced descriptions saved in 'enhanced_description' field")
    print("🔄 Only processing ingredients without existing enhanced descriptions")
    print("✅ Only saves proper enhanced descriptions - no fallback error messages")
    
    if total == 0:
        print("✅ All ingredients already have enhanced descriptions!")
        return

    # 🔹 Smart batch sizing based on primary model (GPT-5)
    if batch_size is None:
        batch_size = 1  # GPT-5: 500 RPM but process one at a time for reliability
    
    print(f"🎯 Using batch size: {batch_size} (GPT-5 rate limit: 500 RPM)")
    
    # Calculate estimated time with conservative rate limiting
    estimated_seconds = total * 15  # With conservative delays: ~15s per ingredient average
    estimated_hours = estimated_seconds / 3600
    print(f"⏱️ Estimated time: ~{estimated_hours:.1f} hours for {total} ingredients (with conservative rate limiting)")
    print(f"💡 Models: GPT-5, ChatGPT-4o-latest, GPT-4.1, GPT-5 variants, GPT-4o variants, GPT-3.5 (up to 3500 RPM)")
    print(f"🔧 Tries each model until one succeeds - no fallback error messages")
    print(f"⏱️ Using 10s delays between requests to avoid daily rate limits")

    async with aiohttp.ClientSession() as session:
        cursor = collection.find(query)
        tasks = []
        processed_count = 0

        pbar = tqdm(total=total, desc="Enriching", unit="ingredient")

        async for ingredient in cursor:
            tasks.append(process_ingredient(session, ingredient))

            if len(tasks) >= batch_size:
                await tqdm_asyncio.gather(*tasks)
                processed_count += len(tasks)
                pbar.update(len(tasks))
                tasks.clear()
                
                # Show progress and remaining time
                remaining = total - processed_count
                if remaining > 0:
                    remaining_time = remaining * 15 / 3600  # hours (with conservative delays: ~15s per ingredient)
                    print(f"\n📊 Progress: {processed_count}/{total} ({processed_count/total*100:.1f}%) - Remaining: {remaining} ingredients (~{remaining_time:.1f} hours)")

        if tasks:
            await tqdm_asyncio.gather(*tasks)
            processed_count += len(tasks)
            pbar.update(len(tasks))

        pbar.close()
        print(f"\n✅ All ingredients processed! Total processed: {processed_count}")

if __name__ == "__main__":
    import sys
    
    # 🔹 Show available models
    if len(sys.argv) > 1 and sys.argv[1] == "--models":
        show_available_models()
    # 🔹 Test mode for debugging the fallback system
    elif len(sys.argv) > 1 and sys.argv[1] == "--test-fallback":
        print("🧪 Testing the fallback system with a simple ingredient...")
        async def test_fallback():
            async with aiohttp.ClientSession() as session:
                test_result = await call_openai(session, "Vitamin C", "Antioxidant vitamin")
                print(f"🧪 Test result: {test_result}")
        
        asyncio.run(test_fallback())
    # 🔹 Cleanup mode - remove all 'Basic' descriptions
    elif len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        print("🧹 Running cleanup mode - removing all 'Basic' descriptions...")
        async def cleanup_only():
            await cleanup_basic_descriptions()
            print("✅ Cleanup completed!")
        
        asyncio.run(cleanup_only())
    # 🔹 Failed processing cleanup mode - remove failed processing entries
    elif len(sys.argv) > 1 and sys.argv[1] == "--cleanup-failed":
        print("🧹 Running failed processing cleanup mode...")
        async def cleanup_failed_only():
            await cleanup_failed_processing_entries()
            print("✅ Failed processing cleanup completed!")
        
        asyncio.run(cleanup_failed_only())
    # 🔹 Deep cleanup mode - remove all enhanced descriptions (nuclear option)
    elif len(sys.argv) > 1 and sys.argv[1] == "--deep-cleanup":
        print("🧹 Running deep cleanup mode - removing ALL enhanced descriptions...")
        async def deep_cleanup():
            total = await collection.count_documents({"enhanced_description": {"$exists": True}})
            if total > 0:
                print(f"⚠️ This will remove {total} enhanced descriptions. Are you sure? (y/N)")
                # For safety, require manual confirmation
                print("⚠️ Deep cleanup requires manual confirmation. Please run the script again with confirmation.")
            else:
                print("✅ No enhanced descriptions found to remove")
        
        asyncio.run(deep_cleanup())
    else:
        asyncio.run(main())
