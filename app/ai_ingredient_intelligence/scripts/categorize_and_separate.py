"""
Categorize ingredients as Active/Excipient and separate them
This is cheaper than full enhancement - just gets the category
Then we can enhance only Actives
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
INPUT_FILE = "cleaned_specialchem_ingredients.json"
OUTPUT_ACTIVES = "cleaned_specialchem_actives.json"
OUTPUT_EXCIPIENTS = "cleaned_specialchem_excipients.json"
CHECKPOINT_FILE = "categorization_checkpoint.json"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""

if not OPENAI_API_KEY:
    print("❌ ERROR: OPENAI_API_KEY not found. Please set it in .env file.")
    exit(1)

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


async def categorize_ingredient(
    session: aiohttp.ClientSession,
    ingredient_name: str,
    description: str
) -> Optional[str]:
    """Categorize ingredient as Active or Excipient (cheaper than full enhancement)"""
    
    clean_ingredient = str(ingredient_name or 'Unknown').strip()
    clean_description = str(description or 'No description available').strip()[:500]  # Limit description
    
    prompt = f"""You are a cosmetic ingredient expert. Categorize this ingredient as ONLY "Active" or "Excipient".

INGREDIENT: {clean_ingredient}
DESCRIPTION: {clean_description[:500]}

Rules:
- "Active": Ingredients with therapeutic, functional, or active properties (vitamins, peptides, acids, retinol, niacinamide, hyaluronic acid, etc.)
- "Excipient": Supporting ingredients (emulsifiers, thickeners, preservatives, solvents, surfactants, emollients, humectants, etc.)

Return ONLY the word "Active" or "Excipient" - nothing else."""

    models_to_try = [
        {"name": "gpt-3.5-turbo", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5-mini", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 30000},
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        endpoint = model_config["endpoint"]
        rpm_limit = model_config["rpm"]
        
        await rate_limiter.wait_if_needed(model_name, rpm_limit)
        await asyncio.sleep(0.5)  # Faster for categorization
        
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
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    if data and "choices" in data:
                        content = data["choices"][0]["message"]["content"].strip().upper()
                        if "ACTIVE" in content:
                            return "Active"
                        elif "EXCIPIENT" in content:
                            return "Excipient"
                
                elif response.status == 429:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "")
                    if "insufficient_quota" in error_msg.lower():
                        return "CREDITS_EXHAUSTED"
                    continue
                else:
                    continue
                    
        except Exception as e:
            continue
    
    return None


def load_checkpoint():
    """Load categorization checkpoint"""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_checkpoint(checkpoint_data):
    """Save categorization checkpoint"""
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, indent=2)


async def main():
    print("=" * 80)
    print("Categorize Ingredients as Active/Excipient")
    print("=" * 80)
    print(f"📥 Input: {INPUT_FILE}")
    print(f"📤 Actives output: {OUTPUT_ACTIVES}")
    print(f"📤 Excipients output: {OUTPUT_EXCIPIENTS}")
    print("=" * 80)
    
    # Load data
    print("\n📖 Loading cleaned data...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total = len(data)
    print(f"✅ Loaded {total} records")
    
    # Load checkpoint
    checkpoint = load_checkpoint()
    categorized_data = checkpoint.get("categorized_data", {})
    start_index = checkpoint.get("last_processed_index", 0)
    credits_exhausted = checkpoint.get("credits_exhausted", False)
    
    if start_index > 0:
        print(f"\n🔄 Resuming from checkpoint: {start_index}/{total} records categorized")
        print(f"   Already categorized: {len(categorized_data)}")
    else:
        print("\n🆕 Starting fresh categorization")
    
    if credits_exhausted:
        print(f"\n❌ Credits exhausted in previous run")
        print(f"   Using existing categorizations: {len(categorized_data)}")
    else:
        # Categorize remaining records
        print(f"\n🤖 Categorizing ingredients (cheaper - just category, no full enhancement)...")
        
        actives_count = sum(1 for cat in categorized_data.values() if cat == "Active")
        excipients_count = sum(1 for cat in categorized_data.values() if cat == "Excipient")
        
        async with aiohttp.ClientSession() as session:
            pbar = tqdm(
                enumerate(data[start_index:], start=start_index),
                desc="Categorizing",
                total=total,
                initial=start_index,
                unit="records"
            )
            
            for idx, record in pbar:
                ingredient_name = record.get("ingredient_name", "")
                description = record.get("description", "")
                
                # Skip if already categorized
                if idx in categorized_data:
                    continue
                
                # Categorize
                category = await categorize_ingredient(session, ingredient_name, description)
                
                if category == "CREDITS_EXHAUSTED":
                    print(f"\n❌ CREDITS EXHAUSTED!")
                    credits_exhausted = True
                    save_checkpoint({
                        "last_processed_index": idx,
                        "categorized_data": categorized_data,
                        "credits_exhausted": True
                    })
                    break
                
                if category:
                    categorized_data[idx] = category
                    if category == "Active":
                        actives_count += 1
                    else:
                        excipients_count += 1
                
                pbar.set_postfix({
                    'actives': actives_count,
                    'excipients': excipients_count,
                    'categorized': len(categorized_data)
                })
                
                # Save checkpoint every 100 records
                if (idx + 1) % 100 == 0:
                    save_checkpoint({
                        "last_processed_index": idx + 1,
                        "categorized_data": categorized_data,
                        "credits_exhausted": credits_exhausted
                    })
            
            pbar.close()
    
    # Separate into actives and excipients
    print(f"\n📊 Categorization Summary:")
    print(f"   Total categorized: {len(categorized_data)}/{total}")
    actives_count = sum(1 for cat in categorized_data.values() if cat == "Active")
    excipients_count = sum(1 for cat in categorized_data.values() if cat == "Excipient")
    print(f"   ✅ Actives: {actives_count}")
    print(f"   ✅ Excipients: {excipients_count}")
    print(f"   ⏭️  Uncategorized: {total - len(categorized_data)}")
    
    print(f"\n📁 Separating into actives and excipients...")
    
    actives = []
    excipients = []
    uncategorized = []
    
    for idx, record in enumerate(data):
        category = categorized_data.get(idx)
        if category == "Active":
            record["category_decided"] = "Active"
            actives.append(record)
        elif category == "Excipient":
            record["category_decided"] = "Excipient"
            excipients.append(record)
        else:
            uncategorized.append(record)
    
    # Save separated files
    print(f"\n💾 Saving separated files...")
    
    with open(OUTPUT_ACTIVES, 'w', encoding='utf-8') as f:
        json.dump(actives, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Actives: {len(actives)} records → {OUTPUT_ACTIVES}")
    
    with open(OUTPUT_EXCIPIENTS, 'w', encoding='utf-8') as f:
        json.dump(excipients, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Excipients: {len(excipients)} records → {OUTPUT_EXCIPIENTS}")
    
    if uncategorized:
        print(f"   ⚠️  Uncategorized: {len(uncategorized)} records (will be in both files for now)")
        # Add uncategorized to both for safety
        for record in uncategorized:
            if record not in actives:
                actives.append(record)
            if record not in excipients:
                excipients.append(record)
    
    # Remove checkpoint on success
    if os.path.exists(CHECKPOINT_FILE) and not credits_exhausted and len(categorized_data) == total:
        os.remove(CHECKPOINT_FILE)
        print(f"\n🗑️  Removed checkpoint (categorization complete)")
    
    print(f"\n✅ Separation complete!")
    print(f"   📁 Actives file: {OUTPUT_ACTIVES} ({len(actives)} records)")
    print(f"   📁 Excipients file: {OUTPUT_EXCIPIENTS} ({len(excipients)} records)")
    print(f"\n💡 Next step: Run enhancement script only on {OUTPUT_ACTIVES}")

if __name__ == "__main__":
    asyncio.run(main())

