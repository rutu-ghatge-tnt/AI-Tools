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

# Read env vars - required, no defaults
MONGO_URI: str = os.getenv("MONGO_URI") or ""
DB_NAME: str = os.getenv("DB_NAME") or ""

if not MONGO_URI:
    raise RuntimeError("ERROR: MONGO_URI is missing. Please set it in your .env file.")
if not DB_NAME:
    raise RuntimeError("ERROR: DB_NAME is missing. Please set it in your .env file.")
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
        
        # Check if we need to wait (use 80% of limit for better utilization)
        aggressive_limit = int(rpm_limit * 0.8)
        if len(self.requests[model_name]) >= aggressive_limit:
            oldest_request = min(self.requests[model_name])
            wait_time = 60 - (current_time - oldest_request) + 1  # Reduced buffer to 1 second
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


# ------------------ Rate Limit Optimization ------------------ #
def calculate_optimal_batch_size(model_name: str, endpoint: str) -> int:
    """Calculate optimal batch size based on OpenAI rate limits and model capabilities"""
    
    # 🔹 Much more aggressive batch sizes for faster processing
    if model_name == "gpt-5":
        # GPT-5: 500 RPM, 30K TPM - can handle more concurrent requests
        return 5  # Increased from 1 to 5 for parallel processing
    elif model_name == "gpt-3.5-turbo-instruct":
        # GPT-3.5-turbo-instruct: 3,500 RPM, 90K TPM - very high limits
        return 20  # Increased from 10 to 20 for maximum speed
    elif model_name == "gpt-3.5-turbo":
        # GPT-3.5-turbo: 500 RPM, 200K TPM - high limits
        return 15  # High batch size for speed
    elif model_name.startswith("gpt-4"):
        # GPT-4 models: 500 RPM, 30K TPM
        return 8  # Good batch size for GPT-4
    elif model_name.startswith("gpt-5"):
        # Other GPT-5 variants: 500 RPM, 200K TPM
        return 10  # High batch size for GPT-5 variants
    
    return 5  # Default to 5 instead of 1

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

    # 🔹 Speed-optimized model priority (fastest models first for bulk processing)
    models_to_try = [
        # Fastest models first for maximum speed
        {"name": "gpt-3.5-turbo-instruct", "max_tokens": 4000, "endpoint": "completions", "rpm": 3500, "tpm": 90000},
        {"name": "gpt-3.5-turbo", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        
        # GPT-5 models (high quality, good speed)
        {"name": "gpt-5-mini", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-mini-2025-08-07", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-nano", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-chat-latest", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-2025-08-07", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        
        # GPT-4 models as fallback
        {"name": "gpt-4o", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4.1", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4o-2024-11-20", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "chatgpt-4o-latest", "max_tokens": 4000, "endpoint": "chat", "rpm": 200, "tpm": 500000}
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        endpoint = model_config["endpoint"]
        rpm_limit = model_config["rpm"]
        
        print(f"🔄 Trying {model_name} ({endpoint} endpoint)...")
        
        # Check rate limits before making request
        await rate_limiter.wait_if_needed(model_name, rpm_limit)
        
        # Reduced delay for faster processing (only 1 second between requests)
        await asyncio.sleep(1)  # Reduced from 10s to 1s for much faster processing
        
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
async def main(batch_size: int = None) -> None:  # Speed-optimized processing
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
    print("🚀 SPEED-OPTIMIZED: Fastest models first with aggressive batch processing!")
    print("📝 Original descriptions will be preserved, enhanced descriptions saved in 'enhanced_description' field")
    print("🔄 Only processing ingredients without existing enhanced descriptions")
    print("✅ Only saves proper enhanced descriptions - no fallback error messages")
    
    if total == 0:
        print("✅ All ingredients already have enhanced descriptions!")
        return

    # 🔹 Aggressive batch sizing for maximum speed
    if batch_size is None:
        batch_size = 20  # Much larger batch size for parallel processing
    
    print(f"🎯 Using batch size: {batch_size} (SPEED-OPTIMIZED parallel processing)")
    
    # Calculate estimated time with optimized processing
    estimated_seconds = total * 2  # Much faster with 1s delays and parallel processing
    estimated_hours = estimated_seconds / 3600
    print(f"⏱️ Estimated time: ~{estimated_hours:.1f} hours for {total} ingredients (SPEED-OPTIMIZED)")
    print(f"💡 Models: GPT-3.5-turbo-instruct (fastest), GPT-3.5-turbo, GPT-5 variants, GPT-4 (fallback)")
    print(f"🔧 Uses fastest models first for maximum speed")
    print(f"⏱️ Using 1s delays between requests for maximum throughput")

    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(20)  # Allow up to 20 concurrent requests
    
    async def process_ingredient_with_semaphore(session: aiohttp.ClientSession, ingredient: Dict[str, Any]) -> None:
        async with semaphore:
            await process_ingredient(session, ingredient)

    async with aiohttp.ClientSession() as session:
        cursor = collection.find(query)
        tasks = []
        processed_count = 0

        pbar = tqdm(total=total, desc="Enriching", unit="ingredient")

        async for ingredient in cursor:
            tasks.append(process_ingredient_with_semaphore(session, ingredient))

            if len(tasks) >= batch_size:
                await tqdm_asyncio.gather(*tasks)
                processed_count += len(tasks)
                pbar.update(len(tasks))
                tasks.clear()
                
                # Show progress and remaining time
                remaining = total - processed_count
                if remaining > 0:
                    remaining_time = remaining * 2 / 3600  # hours (with optimized processing: ~2s per ingredient)
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
    else:
        asyncio.run(main())
