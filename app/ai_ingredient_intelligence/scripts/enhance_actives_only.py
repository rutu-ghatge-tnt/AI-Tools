"""
Enhance descriptions for Active ingredients only
This script takes the separated actives file and enhances descriptions
"""

import json
import os
import asyncio
import aiohttp
import time
from collections import defaultdict
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# Configuration
INPUT_FILE = "cleaned_specialchem_actives.json"  # Actives only
OUTPUT_FILE = "cleaned_specialchem_actives_enhanced.json"
CHECKPOINT_FILE = "enhancement_actives_checkpoint.json"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""

if not OPENAI_API_KEY:
    print("❌ ERROR: OPENAI_API_KEY not found. Please set it in .env file.")
    exit(1)

# Import the enhancement function from clean script
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Rate limiter
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)
    
    async def wait_if_needed(self, model_name: str, rpm_limit: int):
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


async def enhance_description_with_openai(
    session: aiohttp.ClientSession,
    ingredient_name: str,
    description: str
) -> Optional[Dict[str, Any]]:
    """Call OpenAI to enhance description and determine category"""
    
    clean_ingredient = str(ingredient_name or 'Unknown').strip()
    clean_description = str(description or 'No description available').strip()
    
    prompt = f"""You are a cosmetic ingredient expert. Analyze this ACTIVE ingredient and provide a response in EXACT JSON format.

INGREDIENT: {clean_ingredient}
DESCRIPTION: {clean_description}

Provide a JSON response with these exact fields:
{{
    "category": "Active",
    "description": "Enhanced description (~100 words for Active ingredients)"
}}

IMPORTANT: 
- Output ONLY valid JSON, no other text, no markdown, no explanations
- This is an Active ingredient - provide detailed description (~100 words)
- Keep descriptions informative and professional
- Ensure JSON is properly formatted with double quotes"""

    models_to_try = [
        {"name": "gpt-5", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-chat-latest", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-mini", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-4.1", "max_tokens": 4000, "endpoint": "chat", "rpm": 500, "tpm": 30000},
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
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}]
            }
            if model_name.startswith("gpt-5"):
                payload["max_completion_tokens"] = max_tokens
            else:
                payload["max_tokens"] = max_tokens
            
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    if not data or "choices" not in data:
                        continue
                    
                    content = data["choices"][0]["message"]["content"].strip()
                    
                    # Try to extract JSON
                    import re
                    json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            result = json.loads(json_match.group())
                            if "category" in result and "description" in result:
                                return result
                        except json.JSONDecodeError:
                            pass
                    
                    try:
                        result = json.loads(content)
                        if "category" in result and "description" in result:
                            return result
                    except json.JSONDecodeError:
                        continue
                
                elif response.status == 429:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "")
                    if "insufficient_quota" in error_msg.lower():
                        return {"error": "insufficient_quota", "message": error_msg}
                    continue
                else:
                    continue
                    
        except Exception as e:
            continue
    
    return None


def load_checkpoint():
    """Load checkpoint"""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_checkpoint(checkpoint_data):
    """Save checkpoint"""
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, indent=2)


async def main():
    print("=" * 80)
    print("Enhance Active Ingredients Only")
    print("=" * 80)
    print(f"📥 Input: {INPUT_FILE} (actives only)")
    print(f"📤 Output: {OUTPUT_FILE}")
    print("=" * 80)
    
    if not os.path.exists(INPUT_FILE):
        print(f"\n❌ ERROR: {INPUT_FILE} not found!")
        print(f"   Run categorize_and_separate.py first to create the actives file.")
        return
    
    # Load data
    print("\n📖 Loading actives data...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    print(f"✅ Loaded {total} active ingredients")
    
    # Load checkpoint
    checkpoint = load_checkpoint()
    enhanced_data = checkpoint.get("enhanced_data", [])
    start_index = checkpoint.get("last_processed_index", 0)
    credits_exhausted = checkpoint.get("credits_exhausted", False)
    
    if start_index > 0:
        print(f"\n🔄 Resuming from checkpoint: {start_index}/{total} records enhanced")
        data = enhanced_data + data[start_index:]
    else:
        enhanced_data = []
    
    if credits_exhausted:
        print(f"\n❌ Credits exhausted in previous run")
        print(f"   Already enhanced: {len(enhanced_data)}")
    else:
        # Enhance remaining
        print(f"\n🤖 Enhancing descriptions for Active ingredients...")
        
        enhanced_count = len([r for r in enhanced_data if r.get("enhanced_description")])
        
        async with aiohttp.ClientSession() as session:
            pbar = tqdm(
                enumerate(data[start_index:], start=start_index),
                desc="Enhancing",
                total=total,
                initial=start_index,
                unit="records"
            )
            
            for idx, record in pbar:
                ingredient_name = record.get("ingredient_name", "")
                description = record.get("description", "")
                
                # Skip if already enhanced
                if record.get("enhanced_description"):
                    enhanced_data.append(record)
                    continue
                
                # Enhance
                result = await enhance_description_with_openai(session, ingredient_name, description)
                
                if result and result.get("error") == "insufficient_quota":
                    print(f"\n❌ CREDITS EXHAUSTED!")
                    credits_exhausted = True
                    # Save what we have
                    enhanced_data.extend(data[start_index:idx])
                    save_checkpoint({
                        "last_processed_index": idx,
                        "enhanced_data": enhanced_data,
                        "credits_exhausted": True
                    })
                    break
                
                if result and "description" in result:
                    record["enhanced_description"] = result["description"]
                    record["category_decided"] = result.get("category", "Active")
                    enhanced_count += 1
                
                enhanced_data.append(record)
                
                pbar.set_postfix({
                    'enhanced': enhanced_count,
                    'total': len(enhanced_data)
                })
                
                # Save checkpoint every 50 records
                if (idx + 1) % 50 == 0:
                    save_checkpoint({
                        "last_processed_index": idx + 1,
                        "enhanced_data": enhanced_data,
                        "credits_exhausted": credits_exhausted
                    })
            
            pbar.close()
    
    # Save final output
    print(f"\n💾 Saving enhanced actives...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(enhanced_data, f, indent=2, ensure_ascii=False)
    
    enhanced_final = sum(1 for r in enhanced_data if r.get("enhanced_description"))
    print(f"✅ Saved {len(enhanced_data)} active ingredients")
    print(f"   ✅ Enhanced descriptions: {enhanced_final}/{len(enhanced_data)}")
    
    if os.path.exists(CHECKPOINT_FILE) and not credits_exhausted and len(enhanced_data) == total:
        os.remove(CHECKPOINT_FILE)
        print(f"🗑️  Removed checkpoint (enhancement complete)")
    
    print(f"\n✅ Enhancement complete!")
    print(f"   📁 Output: {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())

