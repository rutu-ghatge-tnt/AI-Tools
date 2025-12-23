# app/ai_ingredient_intelligence/scripts/categorize_inci.py
"""Script to categorize INCI ingredients with category (Active/Excipient) and functionality using OpenAI API"""

import os
import json
import asyncio
import aiohttp
import time
import logging
from collections import defaultdict
from datetime import datetime
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm
from typing import Optional, Dict, Any, List

# Configure detailed logging with UTF-8 encoding for Windows compatibility
import sys
log_file = f'categorize_inci_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'

# Create handlers with proper encoding
file_handler = logging.FileHandler(log_file, encoding='utf-8')
console_handler = logging.StreamHandler(sys.stdout)

# Try to set UTF-8 encoding for console on Windows
if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    except:
        pass  # Fallback to default if UTF-8 setup fails

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

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
    raise RuntimeError("ERROR: OPENAI_API_KEY is missing. Please set it in your .env file.")

OPENAI_API_URL: str = "https://api.openai.com/v1/chat/completions"

# Mongo client
client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
collection = db["ingre_inci"]

# Rate limiter to track requests per minute
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
        logger.info("Rate limiter initialized")
    
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
                logger.warning(f"[RATE LIMIT] Rate limit approaching for {model_name}, waiting {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
        
        # Record this request
        self.requests[model_name].append(current_time)

# Global rate limiter
rate_limiter = RateLimiter()

# Available functionality categories for cosmetic ingredients
FUNCTIONALITY_CATEGORIES = [
    "Emulsifier",
    "Stabilizer",
    "Preservative",
    "Humectant",
    "Emollient",
    "Surfactant",
    "Thickener",
    "Antioxidant",
    "Chelating Agent",
    "pH Adjuster",
    "Solvent",
    "Fragrance",
    "Colorant",
    "UV Filter",
    "Skin Conditioning Agent",
    "Exfoliant",
    "Astringent",
    "Film Former",
    "Foaming Agent",
    "Viscosity Modifier",
    "Binding Agent",
    "Opacifying Agent",
    "Pearlescent Agent",
    "Antimicrobial",
    "Deodorant",
    "Hair Conditioning Agent",
    "Hair Styling Agent",
    "Nail Conditioning Agent",
    "Other"
]

def show_functionality_categories():
    """Display available functionality categories"""
    print("\n📋 Available Functionality Categories:")
    print("=" * 60)
    for i, category in enumerate(FUNCTIONALITY_CATEGORIES, 1):
        print(f"  {i:2d}. {category}")
    print("=" * 60)
    print()

# ------------------ Model Information ------------------ #
def show_available_models():
    """Display information about available models and their capabilities"""
    logger.info("🤖 Available Models (tries each until one succeeds):")
    logger.info("   • gpt-5: Primary model (500 RPM, 30K TPM, highest quality)")
    logger.info("   • chatgpt-4o-latest: Latest ChatGPT-4o (200 RPM, 500K TPM, high quality)")
    logger.info("   • gpt-4.1: Stable GPT-4 (500 RPM, 30K TPM, consistent performance)")
    logger.info("   • gpt-5-mini-2025-08-07: GPT-5 Mini variant (500 RPM, 200K TPM)")
    logger.info("   • gpt-5-mini: Compact GPT-5 (500 RPM, 200K TPM, best balance)")
    logger.info("   • gpt-5-chat-latest: Latest GPT-5 variant (500 RPM, 30K TPM)")
    logger.info("   • gpt-3.5-turbo-instruct: Fastest model (3500 RPM, 90K TPM, completions endpoint)")
    logger.info("   • gpt-4o-2024-11-20: GPT-4o variant (500 RPM, 30K TPM)")
    logger.info("   • gpt-3.5-turbo: Fast model (3500 RPM, 90K TPM)")
    logger.info("   • Only saves proper categorizations - no fallback error messages")
    logger.info("")

# ------------------ Rate Limit Optimization ------------------ #
def calculate_optimal_batch_size(model_name: str, endpoint: str) -> int:
    """Calculate optimal batch size based on OpenAI rate limits and model capabilities"""
    
    if model_name == "gpt-5":
        return 5
    elif model_name == "gpt-3.5-turbo-instruct":
        return 20
    elif model_name == "gpt-3.5-turbo":
        return 15
    elif model_name.startswith("gpt-4"):
        return 8
    elif model_name.startswith("gpt-5"):
        return 10
    
    return 5

# ------------------ OpenAI Call ------------------ #
async def call_openai(session: aiohttp.ClientSession,
                      inci_name: Optional[str]) -> Dict[str, Any]:
    """Call OpenAI API to categorize INCI ingredient"""
    
    # Clean and sanitize INCI name
    clean_inci = str(inci_name or 'Unknown').strip()
    
    # Enhanced prompt for categorization
    functionality_list = ", ".join(FUNCTIONALITY_CATEGORIES)
    
    prompt = f"""You are a cosmetic ingredient expert. Analyze this INCI ingredient and provide a response in EXACT JSON format.

INCI NAME: {clean_inci}

Provide a JSON response with these exact fields:
{{
    "category": "Active" or "Excipient",
    "functionality": ["Primary function", "Secondary function (if any)"],
    "reasoning": "Brief explanation of categorization (1-2 sentences)"
}}

CATEGORY RULES (STRICT - ONLY THESE TWO VALUES ALLOWED):
- "Active": Ingredients with therapeutic, functional, or active properties that provide specific benefits (e.g., Niacinamide, Retinol, Salicylic Acid, Hyaluronic Acid, Peptides, Vitamins, Alpha Hydroxy Acids, Beta Hydroxy Acids, Ceramides, Growth Factors)
- "Excipient": Supporting ingredients that provide formulation structure, stability, or delivery but don't have primary active benefits (e.g., Emulsifiers, Thickeners, Preservatives, Solvents, pH Adjusters, Stabilizers, Surfactants, Emollients, Humectants, Colorants, Fragrances)

CRITICAL: The "category" field MUST be exactly "Active" or "Excipient" - NO OTHER VALUES ARE ALLOWED. Do not use "Unknown", "Other", or any other category name.

IMPORTANT DISTINCTION:
- Category = "Active" or "Excipient" (the ingredient's role in the formulation)
- Functionality = What the ingredient does (e.g., Colorant, Emulsifier, Preservative, etc.)
- Colorants, Fragrances, and most formulation aids are typically "Excipient" category, but their functionality would be "Colorant", "Fragrance", etc.

FUNCTIONALITY RULES:
- Select from these categories: {functionality_list}
- Provide 1-2 functionalities (primary and secondary if applicable)
- Use exact category names from the list above
- If multiple functions apply, list them in order of importance
- If none fit perfectly, use "Other" and explain in reasoning
- Remember: Functionality describes WHAT the ingredient does, Category describes its ROLE (Active vs Excipient)

IMPORTANT: 
- Output ONLY valid JSON, no other text, no markdown, no explanations
- Ensure JSON is properly formatted with double quotes
- The "functionality" field must be an array of strings
- The "category" field MUST be exactly "Active" or "Excipient" - nothing else"""

    # Model priority (fastest models first for bulk processing)
    models_to_try = [
        # Fastest models first
        {"name": "gpt-3.5-turbo-instruct", "max_tokens": 2000, "endpoint": "completions", "rpm": 3500, "tpm": 90000},
        {"name": "gpt-3.5-turbo", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        
        # GPT-5 models (high quality, good speed)
        {"name": "gpt-5-mini", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-mini-2025-08-07", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-nano", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-chat-latest", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-2025-08-07", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        
        # GPT-4 models as fallback
        {"name": "gpt-4o", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4.1", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4o-2024-11-20", "max_tokens": 2000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "chatgpt-4o-latest", "max_tokens": 2000, "endpoint": "chat", "rpm": 200, "tpm": 500000}
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        endpoint = model_config["endpoint"]
        rpm_limit = model_config["rpm"]
        
        logger.debug(f"[TRYING] Trying {model_name} ({endpoint} endpoint) for {clean_inci}...")
        
        # Check rate limits before making request
        await rate_limiter.wait_if_needed(model_name, rpm_limit)
        
        # Reduced delay for faster processing
        await asyncio.sleep(1)
        
        # Prepare payload based on endpoint type
        if endpoint == "chat":
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}]
            }
            # Add max_tokens based on model type
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
                    
                    # Parse response
                    if not data or "choices" not in data:
                        logger.warning(f"[WARNING] {model_name} returned empty response for {clean_inci} - trying next model")
                        continue
                    
                    # Handle different response formats based on endpoint
                    if endpoint == "chat":
                        content = data["choices"][0]["message"]["content"]
                    else:  # completions endpoint
                        content = data["choices"][0]["text"]
                    
                    if not content or not content.strip():
                        logger.warning(f"[WARNING] {model_name} returned empty content for {clean_inci} - trying next model")
                        continue
                    
                    content = content.strip()
                    
                    # Try to parse JSON from response
                    try:
                        result = json.loads(content)
                    except json.JSONDecodeError:
                        # Try to extract JSON from potential markdown or extra text
                        import re
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            result = json.loads(json_match.group())
                        else:
                            logger.warning(f"[WARNING] {model_name} returned invalid JSON for {clean_inci} - trying next model")
                            logger.debug(f"Raw response: {content[:200]}")
                            continue
                    
                    # Validate required fields
                    if "category" not in result or "functionality" not in result:
                        logger.warning(f"[WARNING] {model_name} missing required fields for {clean_inci} - trying next model")
                        logger.debug(f"Result: {result}")
                        continue
                    
                    # Validate field types
                    if not isinstance(result["category"], str) or not isinstance(result["functionality"], list):
                        logger.warning(f"[WARNING] {model_name} invalid field types for {clean_inci} - trying next model")
                        logger.debug(f"Result: {result}")
                        continue
                    
                    # STRICT VALIDATION: Category must be exactly "Active" or "Excipient"
                    category_normalized = result["category"].strip()
                    if category_normalized not in ["Active", "Excipient"]:
                        logger.warning(f"[WARNING] {model_name} returned invalid category '{result['category']}' for {clean_inci} - must be 'Active' or 'Excipient' only - trying next model")
                        logger.debug(f"Result: {result}")
                        continue
                    
                    # Normalize category to ensure exact case
                    result["category"] = category_normalized
                    
                    # Validate functionality array contains valid categories
                    valid_functionalities = []
                    for func in result["functionality"]:
                        if func in FUNCTIONALITY_CATEGORIES:
                            valid_functionalities.append(func)
                        else:
                            logger.warning(f"[WARNING] Invalid functionality '{func}' for {clean_inci}, using 'Other' instead")
                            valid_functionalities.append("Other")
                    
                    if not valid_functionalities:
                        valid_functionalities = ["Other"]
                    
                    result["functionality"] = valid_functionalities
                    
                    logger.info(f"[SUCCESS] {model_name} successful for {clean_inci}: {result['category']} - {', '.join(result['functionality'])}")
                    return result
                
                elif response.status == 403:
                    error_text = await response.text()
                    logger.warning(f"[WARNING] {model_name} HTTP 403 for {clean_inci}: {error_text}")
                    logger.info(f"[ERROR] {model_name} not available, trying next model...")
                    continue
                
                elif response.status == 429:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "Rate limit")
                    logger.warning(f"[WARNING] {model_name} rate limit for {clean_inci}: {error_msg}")
                    
                    if "requests per day" in error_msg.lower() or "tokens per day" in error_msg.lower():
                        logger.info(f"[INFO] {model_name} daily limit reached - trying next model...")
                    else:
                        logger.info(f"[INFO] {model_name} minute limit - trying next model...")
                    continue
                
                else:
                    error_text = await response.text()
                    logger.warning(f"[WARNING] {model_name} HTTP {response.status} for {clean_inci}: {error_text[:200]} - trying next model...")
                    continue
                    
        except Exception as e:
            logger.error(f"[ERROR] {model_name} error for {clean_inci}: {e} - trying next model...")
            logger.debug(f"Exception details: {str(e)}", exc_info=True)
            continue
    
    # If all models fail, return None
    logger.error(f"[ERROR] All models failed for {clean_inci} - skipping this ingredient")
    return None


# ------------------ Worker ------------------ #
async def process_ingredient(session: aiohttp.ClientSession, ingredient: Dict[str, Any]) -> None:
    inci_name = ingredient.get("inciName", "Unknown INCI")
    doc_id = ingredient.get("_id")

    try:
        logger.info(f"[PROCESSING] Processing: {inci_name} (ID: {doc_id})")
        result = await call_openai(session, inci_name)
        
        # Only save if we got a proper result
        if result and "category" in result and "functionality" in result:
            update_data = {
                "category": result["category"],
                "functionality": result["functionality"]
            }
            
            # Add reasoning if available
            if "reasoning" in result:
                update_data["categorization_reasoning"] = result["reasoning"]
            
            await collection.update_one(
                {"_id": doc_id},
                {"$set": update_data}
            )
            logger.info(f"[SAVED] Saved categorization for {inci_name}: {result['category']} - {', '.join(result['functionality'])}")
        else:
            logger.warning(f"[SKIP] Skipping {inci_name} - no proper result from any model")
                    
    except Exception as e:
        logger.error(f"[ERROR] {inci_name} failed completely: {e}")
        logger.debug(f"Exception details for {inci_name}: {str(e)}", exc_info=True)
        logger.info(f"[SKIP] Skipping {inci_name} - will be retried in next run")


# ------------------ Main ------------------ #
async def main(batch_size: int = None, fix_invalid: bool = False) -> None:
    """Main function to process INCI ingredients
    
    Args:
        batch_size: Number of ingredients to process in parallel
        fix_invalid: If True, also reprocess ingredients with invalid categories (not "Active" or "Excipient")
    """
    
    total_in_db = await collection.count_documents({})
    
    # Build query: process ingredients without category OR with invalid categories (if fix_invalid is True)
    if fix_invalid:
        # Process ingredients that don't have category OR have invalid categories
        query: Dict[str, Any] = {
            "$or": [
                {"category": {"$exists": False}},
                {"category": {"$nin": ["Active", "Excipient"]}}
            ]
        }
        logger.info("[INFO] Mode: Processing new ingredients AND fixing invalid categories")
    else:
        # Process only ingredients that don't have category yet
        query: Dict[str, Any] = {"category": {"$exists": False}}
        logger.info("[INFO] Mode: Processing only ingredients without category field")
    
    total = await collection.count_documents(query)
    
    # Count already processed ingredients with valid categories
    already_processed = await collection.count_documents({
        "category": {"$in": ["Active", "Excipient"]}
    })
    
    # Count ingredients with invalid categories (if any)
    invalid_categories = await collection.count_documents({
        "category": {"$exists": True, "$nin": ["Active", "Excipient"]}
    })
    
    logger.info("=" * 80)
    logger.info("[START] INCI Ingredient Categorization Script")
    logger.info("=" * 80)
    logger.info(f"[INFO] Database: {DB_NAME}")
    logger.info(f"[INFO] Collection: ingre_inci")
    logger.info(f"[INFO] Total documents in database: {total_in_db}")
    logger.info(f"[INFO] Already processed (valid categories): {already_processed} ingredients")
    if invalid_categories > 0:
        logger.info(f"[WARNING] Found {invalid_categories} ingredients with invalid categories (will be fixed)")
    logger.info(f"[INFO] Processing: {total} ingredients")
    logger.info(f"[INFO] Using MONGO_URI: {MONGO_URI}")
    logger.info("=" * 80)
    show_functionality_categories()
    
    if total == 0:
        logger.info("[INFO] All ingredients already have category field!")
        return

    # Aggressive batch sizing for maximum speed
    if batch_size is None:
        batch_size = 20
    
    logger.info(f"[INFO] Using batch size: {batch_size} (parallel processing)")
    
    # Calculate estimated time
    estimated_seconds = total * 2  # ~2s per ingredient with parallel processing
    estimated_hours = estimated_seconds / 3600
    logger.info(f"[INFO] Estimated time: ~{estimated_hours:.1f} hours for {total} ingredients")
    logger.info(f"[INFO] Models: GPT-3.5-turbo-instruct (fastest), GPT-3.5-turbo, GPT-5 variants, GPT-4 (fallback)")
    logger.info(f"[INFO] Uses fastest models first for maximum speed")
    logger.info(f"[INFO] Using 1s delays between requests for maximum throughput")
    logger.info("")

    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(20)  # Allow up to 20 concurrent requests
    
    async def process_ingredient_with_semaphore(session: aiohttp.ClientSession, ingredient: Dict[str, Any]) -> None:
        async with semaphore:
            await process_ingredient(session, ingredient)

    stats = {
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "skipped": 0
    }

    async with aiohttp.ClientSession() as session:
        cursor = collection.find(query)
        tasks = []
        processed_count = 0

        pbar = tqdm(total=total, desc="Categorizing", unit="ingredient")

        async for ingredient in cursor:
            tasks.append(process_ingredient_with_semaphore(session, ingredient))

            if len(tasks) >= batch_size:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                # Log any exceptions
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Task failed with exception: {result}")
                processed_count += len(tasks)
                pbar.update(len(tasks))
                tasks.clear()
                
                # Show progress and remaining time
                remaining = total - processed_count
                if remaining > 0:
                    remaining_time = remaining * 2 / 3600  # hours
                    logger.info(f"[PROGRESS] Progress: {processed_count}/{total} ({processed_count/total*100:.1f}%) - Remaining: {remaining} ingredients (~{remaining_time:.1f} hours)")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Log any exceptions
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Task failed with exception: {result}")
            processed_count += len(tasks)
            pbar.update(len(tasks))

        pbar.close()
        
        # Final statistics
        final_valid = await collection.count_documents({"category": {"$in": ["Active", "Excipient"]}})
        final_invalid = await collection.count_documents({"category": {"$exists": True, "$nin": ["Active", "Excipient"]}})
        final_no_category = await collection.count_documents({"category": {"$exists": False}})
        logger.info("")
        logger.info("=" * 80)
        logger.info("[COMPLETE] Processing Complete!")
        logger.info(f"[STATS] Total processed in this run: {processed_count}")
        logger.info(f"[STATS] Total with valid category (Active/Excipient): {final_valid}")
        if final_invalid > 0:
            logger.info(f"[WARNING] Total with invalid category: {final_invalid} (run with --fix-invalid to fix)")
        logger.info(f"[STATS] Remaining without category: {final_no_category}")
        logger.info("=" * 80)

if __name__ == "__main__":
    import sys
    
    # Show available models
    if len(sys.argv) > 1 and sys.argv[1] == "--models":
        show_available_models()
    # Show functionality categories
    elif len(sys.argv) > 1 and sys.argv[1] == "--categories":
        show_functionality_categories()
    # Test mode for debugging
    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        logger.info("[TEST] Testing the categorization system with sample ingredients...")
        async def test_categorization():
            async with aiohttp.ClientSession() as session:
                test_ingredients = ["Niacinamide", "Glycerin", "Sodium Lauryl Sulfate", "Retinol"]
                for ingredient in test_ingredients:
                    logger.info(f"\n[TEST] Testing: {ingredient}")
                    test_result = await call_openai(session, ingredient)
                    logger.info(f"[TEST] Result: {json.dumps(test_result, indent=2)}")
        
        asyncio.run(test_categorization())
    # Fix invalid categories mode
    elif len(sys.argv) > 1 and sys.argv[1] == "--fix-invalid":
        logger.info("[INFO] Running in fix-invalid mode: will reprocess ingredients with invalid categories")
        asyncio.run(main(fix_invalid=True))
    else:
        asyncio.run(main(fix_invalid=False))

