# app/ai_ingredient_intelligence/scripts/enrich_description.py
"""Script to enrich ingredient descriptions using LLM"""

import os
import json
import random
import asyncio
import aiohttp
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


# ------------------ Model Information ------------------ #
def show_available_models():
    """Display information about available models and their capabilities"""
    print("🤖 Available Models for Fallback:")
    print("   • gpt-5: Primary model (3 RPM, highest quality)")
    print("   • gpt-5-chat-latest: Latest GPT-5 variant (faster fallback)")
    print("   • gpt-5-mini: Compact GPT-5 (good balance of speed/quality)")
    print("   • gpt-4o: Latest GPT-4 (fast, reliable)")
    print("   • gpt-4.1: Stable GPT-4 (consistent performance)")
    print("   • gpt-3.5-turbo-instruct: Fastest fallback (completions endpoint)")
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

    # 🔹 Use GPT-5 as primary with intelligent fallbacks to available models
    models_to_try = [
        {"name": "gpt-5", "max_tokens": 1000, "delay": 20, "retries": 3, "endpoint": "chat"},
        {"name": "gpt-5-chat-latest", "max_tokens": 1000, "delay": 15, "retries": 2, "endpoint": "chat"},
        {"name": "gpt-5-mini", "max_tokens": 1000, "delay": 10, "retries": 2, "endpoint": "chat"},
        {"name": "gpt-4o", "max_tokens": 1000, "delay": 8, "retries": 2, "endpoint": "chat"},
        {"name": "gpt-4.1", "max_tokens": 1000, "delay": 8, "retries": 2, "endpoint": "chat"},
        {"name": "gpt-3.5-turbo-instruct", "max_tokens": 1000, "delay": 5, "retries": 2, "endpoint": "completions"}
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        delay = model_config["delay"]
        max_retries = model_config["retries"]
        endpoint = model_config["endpoint"]
        
        print(f"🔄 Trying {model_name} ({endpoint} endpoint)...")
        
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
        
        for attempt in range(max_retries):
            # 🔹 Minimal delay between attempts (only for rate limits)
            if attempt > 0:
                await asyncio.sleep(0.5)  # Reduced from 1s to 0.5s
                
            try:
                # 🔹 Use correct endpoint based on model type
                api_url = "https://api.openai.com/v1/chat/completions" if endpoint == "chat" else "https://api.openai.com/v1/completions"
                
                async with session.post(
                    api_url,
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    
                    # 🔹 Check rate limit headers first (more accurate than parsing errors)
                    if response.status == 200:
                        # 🔹 Extract rate limit info from headers
                        remaining_requests = response.headers.get('x-ratelimit-remaining-requests', 'unknown')
                        remaining_tokens = response.headers.get('x-ratelimit-remaining-tokens', 'unknown')
                        reset_requests = response.headers.get('x-ratelimit-reset-requests', 'unknown')
                        reset_tokens = response.headers.get('x-ratelimit-reset-tokens', 'unknown')
                        
                        if remaining_requests == '0' or remaining_tokens == '0':
                            print(f"⚠️ Rate limit approaching for {model_name}: Requests={remaining_requests}, Tokens={remaining_tokens}")
                    
                    if response.status == 429:
                        # 🔹 Parse rate limit error with exponential backoff + jitter
                        error_data = await response.json()
                        error_msg = error_data.get("error", {}).get("message", "Unknown rate limit error")
                        
                        # 🔹 Faster rate limit handling - switch models quickly instead of waiting
                        if "requests per day" in error_msg.lower():
                            print(f"⚠️ Daily rate limit reached for {model_name}. Switching to next model...")
                            break  # Try next model immediately
                            
                        elif "requests per min" in error_msg.lower() or "tokens per min" in error_msg.lower():
                            # 🔹 For minute-based rate limits, wait only 10 seconds max
                            wait_time = min(10, 5 * (attempt + 1))  # 5s, 10s, 10s
                            print(f"⏱️ Rate limit hit for {model_name}. Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                            await asyncio.sleep(wait_time)
                            continue
                        
                        else:
                            # 🔹 For unknown rate limits, wait only 5 seconds max
                            wait_time = min(5, 2 * (attempt + 1))  # 2s, 4s, 5s
                            print(f"⚠️ Unknown rate limit for {model_name}: {error_msg}")
                            print(f"⏱️ Quick retry: waiting {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            continue
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # 🔹 Debug: Show raw response structure
                        print(f"🔍 {model_name} response structure: {list(data.keys()) if data else 'None'}")
                        if data and "choices" in data:
                            print(f"🔍 {model_name} choices count: {len(data['choices'])}")
                        
                        # 🔹 Parse response with better error handling
                        try:
                            if not data or "choices" not in data:
                                raise ValueError("Empty or invalid response structure")
                            
                            # 🔹 Handle different response formats based on endpoint
                            if endpoint == "chat":
                                content = data["choices"][0]["message"]["content"]
                                print(f"🔍 {model_name} chat content length: {len(content) if content else 'None'}")
                            else:  # completions endpoint
                                content = data["choices"][0]["text"]
                                print(f"🔍 {model_name} completions text length: {len(content) if content else 'None'}")
                            
                            # 🔹 Fast fail for None content - don't waste time retrying
                            if not content:
                                print(f"⚠️ {model_name} returned None content - skipping to next model")
                                break  # Skip to next model immediately
                            
                            content = content.strip()
                            if not content:
                                print(f"⚠️ {model_name} returned empty content after stripping - skipping to next model")
                                break  # Skip to next model immediately
                            
                            print(f"🔍 {model_name} stripped content preview: {content[:100]}...")
                            
                            # 🔹 Try to parse JSON from response with better error handling
                            try:
                                result = json.loads(content)
                            except json.JSONDecodeError as e:
                                # 🔹 Try to extract JSON from potential markdown or extra text
                                import re
                                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                                if json_match:
                                    try:
                                        result = json.loads(json_match.group())
                                    except:
                                        raise ValueError(f"Could not extract valid JSON from: {content[:100]}...")
                                else:
                                    raise ValueError(f"No JSON found in response: {content[:100]}...")
                            
                            # 🔹 Validate required fields
                            if "category" not in result or "description" not in result:
                                raise ValueError(f"Missing required fields. Got: {list(result.keys())}")
                            
                            # 🔹 Validate field types
                            if not isinstance(result["category"], str) or not isinstance(result["description"], str):
                                raise ValueError("Category and description must be strings")
                            
                            print(f"✅ {model_name} successful!")
                            return result
                            
                        except (json.JSONDecodeError, ValueError) as e:
                            print(f"⚠️ {model_name} response parsing error: {e}")
                            print(f"🔍 Raw content: {content[:200] if 'content' in locals() else 'No content'}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1)  # Reduced from 5s to 1s
                                continue
                            else:
                                break  # Try next model
                                
                    else:
                        error_text = await response.text()
                        print(f"⚠️ {model_name} HTTP {response.status}: {error_text}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)  # Reduced from 10s to 2s
                            continue
                        else:
                            break  # Try next model
                            
            except aiohttp.ClientError as e:
                print(f"⚠️ Network error with {model_name}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)  # Reduced from 10s to 2s
                    continue
                else:
                    break  # Try next model
                    
            except asyncio.TimeoutError:
                print(f"⚠️ Timeout with {model_name}")
                if attempt < max_retries - 1:
                    continue
                else:
                    break  # Try next model
                    
            except Exception as e:
                print(f"⚠️ Unexpected error with {model_name}: {e}")
                print(f"🔍 Error type: {type(e).__name__}")
                print(f"🔍 Error details: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)  # Reduced from 10s to 2s
                    continue
                else:
                    break  # Try next model
        
        # 🔹 If we get here, this model failed, try the next one
        print(f"❌ {model_name} failed, trying next model...")
        continue
    
    # 🔹 If all models fail completely, raise an error
    print(f"❌ All models failed completely for {clean_ingredient}")
    raise RuntimeError(f"All available models could not process ingredient: {clean_ingredient}")


# ------------------ Worker ------------------ #
async def process_ingredient(session: aiohttp.ClientSession, ingredient: Dict[str, Any]) -> None:
    name = ingredient.get("ingredient_name", "Unknown Ingredient")
    desc = ingredient.get("description")

    try:
        # 🔹 Add retry logic for the entire ingredient processing
        max_worker_retries = 2
        for worker_attempt in range(max_worker_retries):
            try:
                result = await call_openai(session, name, desc)
                
                # 🔹 Validate result before saving
                if not result or "category" not in result or "description" not in result:
                    raise ValueError(f"Invalid result structure: {result}")
                
                await collection.update_one(
                    {"_id": ingredient["_id"]},
                    {"$set": {
                        "category_decided": result["category"],
                        "enhanced_description": result["description"]
                    }}
                )
                print(f"💾 Saved enhanced description for {name}")
                return  # Success, exit retry loop
                
            except Exception as e:
                print(f"⚠️ Worker attempt {worker_attempt + 1} failed for {name}: {e}")
                if worker_attempt < max_worker_retries - 1:
                    await asyncio.sleep(1)  # Reduced from 5s to 1s
                    continue
                else:
                    # 🔹 Final fallback - save basic info
                    print(f"🔄 Saving fallback data for {name}")
                    await collection.update_one(
                        {"_id": ingredient["_id"]},
                        {"$set": {
                            "category_decided": "Unknown",
                            "enhanced_description": f"Processing failed for {name}. Requires manual review."
                        }}
                    )
                    break
                    
    except Exception as e:
        print(f"❌ {name} failed completely: {e}")
        # 🔹 Save error info for debugging
        try:
            await collection.update_one(
                {"_id": ingredient["_id"]},
                {"$set": {
                    "category_decided": "Error",
                    "enhanced_description": f"Processing error: {str(e)}"
                }}
            )
        except:
            print(f"⚠️ Could not save error info for {name}")


# ------------------ Main ------------------ #
async def main(batch_size: int = None) -> None:  # GPT-5 only processing
    # 🔹 First, clean up any existing 'Basic' descriptions
    await cleanup_basic_descriptions()
    
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
    print("🚀 Using GPT-5 as primary with intelligent fallbacks to available models!")
    print("📝 Original descriptions will be preserved, enhanced descriptions saved in 'enhanced_description' field")
    print("🔄 Only processing ingredients without existing enhanced descriptions")
    
    if total == 0:
        print("✅ All ingredients already have enhanced descriptions!")
        return

    # 🔹 Smart batch sizing based on primary model (GPT-5)
    if batch_size is None:
        batch_size = 1  # GPT-5: 3 RPM = process one at a time
    
    print(f"🎯 Using batch size: {batch_size} (GPT-5 rate limit: 3 RPM)")
    
    # Calculate estimated time with fallback models (faster than GPT-5 only)
    estimated_seconds = total * 15  # With fallbacks: ~15s per ingredient average
    estimated_hours = estimated_seconds / 3600
    print(f"⏱️ Estimated time: ~{estimated_hours:.1f} hours for {total} ingredients (with fallbacks)")
    print(f"💡 Primary: GPT-5 (3 RPM), Fallbacks: GPT-5 variants, GPT-4, GPT-3.5")
    print(f"🔧 Using intelligent fallback system with exponential backoff")

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
                    remaining_time = remaining * 15 / 3600  # hours (with fallbacks: ~15s per ingredient)
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
