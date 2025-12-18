"""
Categorize ingredients as Active or Excipient using OpenAI
This script reads cleaned data and adds category_decided field
"""

import json
import os
import asyncio
import aiohttp
import time
import shutil
from datetime import datetime
from collections import defaultdict
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Configuration
INPUT_FILE = "cleaned_specialchem_ingredients.json"
OUTPUT_FILE = "cleaned_specialchem_ingredients.json"  # Overwrite with categories
CHECKPOINT_FILE = "categorization_checkpoint.json"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""

if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY is missing. Please set it in your .env file.")

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
    """Categorize ingredient as Active or Excipient"""
    
    clean_ingredient = str(ingredient_name or 'Unknown').strip()
    clean_description = str(description or 'No description available').strip()
    
    prompt = f"""You are a cosmetic ingredient expert. Categorize this ingredient as either "Active" or "Excipient".

INGREDIENT: {clean_ingredient}
DESCRIPTION: {clean_description}

Rules:
- "Active": Ingredients with therapeutic, functional, or active properties that provide specific benefits (e.g., Niacinamide, Retinol, Salicylic Acid, Hyaluronic Acid, Peptides, Vitamins, Alpha Hydroxy Acids, Beta Hydroxy Acids, Ceramides, Growth Factors, Antioxidants, Anti-aging agents)
- "Excipient": Supporting ingredients that provide formulation structure, stability, or delivery but don't have primary active benefits (e.g., Emulsifiers, Thickeners, Preservatives, Solvents, pH Adjusters, Stabilizers, Surfactants, Emollients, Humectants, Colorants, Fragrances, Gelling agents)

CRITICAL: Return ONLY "Active" or "Excipient" - nothing else, no explanation, no JSON, just the word."""

    # Model priority (Fastest/cheapest first for categorization)
    models_to_try = [
        {"name": "gpt-3.5-turbo", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 200000},  # Cheapest and fast
        {"name": "gpt-5-mini", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 200000},  # Fast and cheap
        {"name": "gpt-5-mini-2025-08-07", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 200000},
        {"name": "gpt-5", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-5-chat-latest", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "gpt-4.1", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 30000},
        {"name": "chatgpt-4o-latest", "max_tokens": 10, "endpoint": "chat", "rpm": 200, "tpm": 500000},
        {"name": "gpt-4o-2024-11-20", "max_tokens": 10, "endpoint": "chat", "rpm": 500, "tpm": 30000},
    ]
    
    for model_config in models_to_try:
        model_name = model_config["name"]
        max_tokens = model_config["max_tokens"]
        endpoint = model_config["endpoint"]
        rpm_limit = model_config["rpm"]
        
        await rate_limiter.wait_if_needed(model_name, rpm_limit)
        await asyncio.sleep(0.1)  # Minimal delay for faster processing
        
        try:
            if endpoint == "chat":
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}]
                }
                if model_name.startswith("gpt-5"):
                    payload["max_completion_tokens"] = max_tokens
                else:
                    payload["max_tokens"] = max_tokens
            else:
                payload = {
                    "model": model_name,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": 0.1,
                }
            
            api_url = "https://api.openai.com/v1/chat/completions" if endpoint == "chat" else "https://api.openai.com/v1/completions"
            
            async with session.post(
                api_url,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    if not data or "choices" not in data:
                        continue
                    
                    if endpoint == "chat":
                        content = data["choices"][0]["message"]["content"].strip().upper()
                    else:
                        content = data["choices"][0]["text"].strip().upper()
                    
                    # Extract category
                    if "ACTIVE" in content:
                        return "Active"
                    elif "EXCIPIENT" in content:
                        return "Excipient"
                
                elif response.status == 429:
                    error_data = await response.json()
                    error_msg = error_data.get("error", {}).get("message", "")
                    if "insufficient_quota" in error_msg.lower() or "billing" in error_msg.lower():
                        return "CREDITS_EXHAUSTED"
                    continue
                elif response.status == 401:
                    return "INVALID_KEY"
                else:
                    continue
                    
        except Exception as e:
            continue
    
    return None


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
    """Main categorization function"""
    
    print("=" * 80)
    print("Ingredient Categorization (Active vs Excipient)")
    print("=" * 80)
    print(f"📥 Input file: {INPUT_FILE}")
    print(f"📤 Output file: {OUTPUT_FILE}")
    print(f"💾 Checkpoint file: {CHECKPOINT_FILE}")
    print("=" * 80)
    
    # Create backup before loading (to prevent data loss)
    backup_file = f"{INPUT_FILE}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if os.path.exists(INPUT_FILE):
        print(f"\n💾 Creating backup: {backup_file}")
        shutil.copy2(INPUT_FILE, backup_file)
        # Keep only last 3 backups
        import glob
        backups = sorted(glob.glob(f"{INPUT_FILE}.backup_*"), reverse=True)
        for old_backup in backups[3:]:
            try:
                os.remove(old_backup)
                print(f"   🗑️  Removed old backup: {os.path.basename(old_backup)}")
            except:
                pass
    
    # Load data first
    print("\n📖 Loading data...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total_records = len(data)
    
    # Recalculate actual counts from data (don't trust checkpoint counts)
    categorized_count = sum(1 for record in data if record.get("category_decided") in ["Active", "Excipient"])
    active_count = sum(1 for record in data if record.get("category_decided") == "Active")
    excipient_count = sum(1 for record in data if record.get("category_decided") == "Excipient")
    
    # Load checkpoint for resume position
    checkpoint = load_checkpoint()
    checkpoint_index = checkpoint.get("last_processed_index", 0)
    
    # Find the first uncategorized item starting from checkpoint (or earlier if needed)
    # This ensures we don't skip uncategorized items that might be before the checkpoint
    start_index = checkpoint_index
    if checkpoint_index > 0:
        # First, check if there are uncategorized items before checkpoint
        found_uncategorized_before = False
        for i in range(checkpoint_index - 1, -1, -1):
            if data[i].get("category_decided") not in ["Active", "Excipient"]:
                start_index = i
                found_uncategorized_before = True
                break
        
        # If no uncategorized before checkpoint, check forward from checkpoint
        if not found_uncategorized_before:
            for i in range(checkpoint_index, total_records):
                if data[i].get("category_decided") not in ["Active", "Excipient"]:
                    start_index = i
                    break
            else:
                # All items are categorized!
                start_index = total_records
    
    uncategorized_count = total_records - categorized_count
    
    if checkpoint_index > 0:
        print(f"\n🔄 CHECKPOINT FOUND - Resuming from previous run")
        if start_index != checkpoint_index:
            print(f"   ⚠️  Found uncategorized items before checkpoint, starting from index {start_index}")
        print(f"   📊 Progress: {categorized_count}/{total_records} categorized ({categorized_count*100/total_records:.1f}%)")
        print(f"   ✅ Already categorized: {categorized_count}")
        print(f"   ⏳ Remaining: {uncategorized_count} uncategorized")
        print(f"   🟢 Active: {active_count}")
        print(f"   🔵 Excipient: {excipient_count}")
        print(f"   ⏭️  Starting processing from record index {start_index}...")
    else:
        print(f"\n🆕 Starting fresh (no checkpoint found)")
        print(f"   📁 Total records: {total_records}")
        print(f"   ✅ Already categorized: {categorized_count}")
        print(f"   ⏳ Remaining: {uncategorized_count} uncategorized")
        print(f"   🟢 Active: {active_count}")
        print(f"   🔵 Excipient: {excipient_count}")
    
    # Check if all records are already categorized
    if categorized_count >= total_records:
        print(f"\n✅ All records are already categorized!")
        print(f"   📊 Total records: {total_records}")
        print(f"   ✅ Categorized: {categorized_count}")
        print(f"   🟢 Active: {active_count}")
        print(f"   🔵 Excipient: {excipient_count}")
        print(f"\n💾 Saving final data...")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)
        print(f"✅ Complete! Output saved to: {OUTPUT_FILE}")
        return
    
    # Process records in parallel batches for speed
    print("\n🏷️  Categorizing ingredients (parallel processing)...")
    
    batch_size = 20  # Process 20 records in parallel
    max_retries = 3  # Retry failed categorizations up to 3 times
    
    async with aiohttp.ClientSession() as session:
        # Track failed records for retry
        failed_records = []  # List of (index, record) tuples that failed
        
        # Calculate total uncategorized records for accurate progress
        def get_uncategorized_indices():
            return [i for i in range(total_records) 
                   if data[i].get("category_decided") not in ["Active", "Excipient"]]
        
        uncategorized_indices = get_uncategorized_indices()
        total_uncategorized = len(uncategorized_indices)
        
        pbar = tqdm(
            total=total_records,
            desc="Categorizing",
            initial=categorized_count,
            unit="records",
            ncols=100,
            bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} records [{elapsed}<{remaining}, {rate_fmt}]'
        )
        
        credits_exhausted = False
        last_processed_index = start_index
        retry_pass = 0
        
        # Main processing loop - continue until all categorized or credits exhausted
        while retry_pass <= max_retries and not credits_exhausted:
            if retry_pass > 0:
                print(f"\n🔄 Retry pass {retry_pass}/{max_retries} - Processing {len(failed_records)} failed records...")
                # Update uncategorized indices for retry (recalculate to get fresh list)
                uncategorized_indices = [idx for idx, _ in failed_records]
                failed_records = []  # Clear for this retry pass
            else:
                # First pass - get all uncategorized records
                uncategorized_indices = get_uncategorized_indices()
            
            if not uncategorized_indices:
                break  # All records are categorized!
            
            # Process in batches
            for batch_start in range(0, len(uncategorized_indices), batch_size):
                batch_indices = uncategorized_indices[batch_start:batch_start + batch_size]
                batch_records = [(idx, data[idx]) for idx in batch_indices]
                last_processed_index = max(batch_indices) if batch_indices else last_processed_index
                
                # Process batch in parallel
                tasks = []
                task_data = []  # Track (index, record) for each task
                
                for idx, record in batch_records:
                    # Skip if already categorized (might have been categorized in previous pass)
                    if record.get("category_decided") in ["Active", "Excipient"]:
                        continue
                    
                    ingredient_name = record.get("ingredient_name", "")
                    description = record.get("description", "")
                    
                    if ingredient_name:
                        tasks.append(categorize_ingredient(session, ingredient_name, description))
                        task_data.append((idx, record))
                
                if not tasks:
                    # All in batch already categorized
                    pbar.set_postfix({
                        'categorized': categorized_count,
                        'active': active_count,
                        'excipient': excipient_count,
                        'failed': len(failed_records),
                        'rate': f"{categorized_count*100/total_records:.1f}%"
                    })
                    continue
                
                try:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Process results
                    for task_idx, result in enumerate(results):
                        record_idx, record = task_data[task_idx]
                        
                        if isinstance(result, Exception):
                            # Track failed record for retry
                            failed_records.append((record_idx, record))
                            continue
                        
                        if result == "CREDITS_EXHAUSTED":
                            credits_exhausted = True
                            print(f"\n❌ CREDITS EXHAUSTED - Stopping categorization")
                            break
                        elif result == "INVALID_KEY":
                            print(f"\n❌ INVALID API KEY - Stopping categorization")
                            credits_exhausted = True
                            break
                        elif result in ["Active", "Excipient"]:
                            # Only count if this is a NEW categorization
                            was_already_categorized = record.get("category_decided") in ["Active", "Excipient"]
                            record["category_decided"] = result
                            if not was_already_categorized:
                                categorized_count += 1
                                if result == "Active":
                                    active_count += 1
                                else:
                                    excipient_count += 1
                                pbar.update(1)  # Update progress for each successful categorization
                        else:
                            # result is None - API call failed, track for retry
                            failed_records.append((record_idx, record))
                    
                    pbar.set_postfix({
                        'categorized': categorized_count,
                        'active': active_count,
                        'excipient': excipient_count,
                        'failed': len(failed_records),
                        'rate': f"{categorized_count*100/total_records:.1f}%"
                    })
                    
                    # Save checkpoint every 100 categorizations
                    if categorized_count % 100 == 0:
                        save_checkpoint({
                            "last_processed_index": last_processed_index,
                            "categorized_count": categorized_count,
                            "active_count": active_count,
                            "excipient_count": excipient_count,
                            "credits_exhausted": credits_exhausted
                        })
                        pbar.set_description(f"Categorizing (saved @ {categorized_count})")
                    
                    if credits_exhausted:
                        break
                        
                except Exception as e:
                    print(f"\n⚠️  Error processing batch: {e}")
                    # Add all records in batch to failed list for retry
                    for idx, record in batch_records:
                        if record.get("category_decided") not in ["Active", "Excipient"]:
                            failed_records.append((idx, record))
                    continue
            
            # Check if we're done (recalculate to account for newly categorized records)
            remaining_uncategorized = get_uncategorized_indices()
            if not remaining_uncategorized:
                break  # All records categorized!
            
            # If we have failed records and haven't exceeded max retries, prepare for retry
            if failed_records and retry_pass < max_retries:
                retry_pass += 1
            else:
                break  # No more retries or no failed records
        
        pbar.close()
        
        # Final check for failed records
        final_failed = get_uncategorized_indices()
        if final_failed and not credits_exhausted:
            print(f"\n⚠️  {len(final_failed)} records remain uncategorized after {retry_pass} pass(es)")
            print(f"   These may have failed API calls or missing ingredient names")
        
        if credits_exhausted:
            save_checkpoint({
                "last_processed_index": last_processed_index,
                "categorized_count": categorized_count,
                "active_count": active_count,
                "excipient_count": excipient_count,
                "credits_exhausted": True
            })
            print(f"\n⏸️  Categorization paused due to credits exhaustion")
            print(f"   ✅ Categorized: {categorized_count}/{total_records}")
            print(f"   🟢 Active: {active_count}")
            print(f"   🔵 Excipient: {excipient_count}")
            print(f"   💡 Run again when credits are available to continue")
        else:
            # Recalculate final counts from actual data (don't trust our running count)
            final_categorized = sum(1 for record in data if record.get("category_decided") in ["Active", "Excipient"])
            final_active = sum(1 for record in data if record.get("category_decided") == "Active")
            final_excipient = sum(1 for record in data if record.get("category_decided") == "Excipient")
            
            # Save final data (with backup of previous version)
            print(f"\n💾 Saving categorized data...")
            if os.path.exists(OUTPUT_FILE):
                # Create backup of current file before overwriting
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                pre_save_backup = f"{OUTPUT_FILE}.pre_save_{timestamp}"
                shutil.copy2(OUTPUT_FILE, pre_save_backup)
                print(f"   💾 Backed up current file to: {os.path.basename(pre_save_backup)}")
            
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Only remove checkpoint if ALL records are categorized
            if final_categorized >= total_records:
                if os.path.exists(CHECKPOINT_FILE):
                    os.remove(CHECKPOINT_FILE)
                print(f"\n✅ Categorization Complete!")
            else:
                # Save checkpoint so we can resume later without re-processing
                save_checkpoint({
                    "last_processed_index": last_processed_index,
                    "categorized_count": final_categorized,
                    "active_count": final_active,
                    "excipient_count": final_excipient,
                    "credits_exhausted": False
                })
                print(f"\n⏸️  Processing paused (not all records categorized)")
            
            print(f"   📊 Total records: {total_records}")
            print(f"   ✅ Categorized: {final_categorized}/{total_records} ({final_categorized*100/total_records:.1f}%)")
            if final_categorized > 0:
                print(f"   🟢 Active: {final_active} ({final_active*100/final_categorized:.1f}%)")
                print(f"   🔵 Excipient: {final_excipient} ({final_excipient*100/final_categorized:.1f}%)")
            print(f"   📁 Output saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())

